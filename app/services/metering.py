import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Plan, Subscription, Tenant, UsageEvent
from app.schemas.api import GenerateRequest, GenerateResponse
from app.services.pricing import calculate_cost


class QuotaExceeded(Exception):
    def __init__(self, usage_type: str, used: int, requested: int, limit: int, status_code: int = 429):
        self.usage_type = usage_type
        self.used = used
        self.requested = requested
        self.limit = limit
        self.status_code = status_code
        super().__init__(f'{usage_type} quota exceeded: used={used}, requested={requested}, limit={limit}')


class IdempotencyConflict(Exception):
    pass


class PaymentRequired(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f'payment required: subscription status is {status}')


class BudgetExceeded(Exception):
    def __init__(self, cost_micro_usd: int, limit_micro_usd: int):
        self.cost_micro_usd = cost_micro_usd
        self.limit_micro_usd = limit_micro_usd
        super().__init__(f'AI request cost budget exceeded: cost={cost_micro_usd}, limit={limit_micro_usd}')


def request_hash(request: GenerateRequest) -> str:
    raw = json.dumps(request.model_dump(), sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def current_usage(db: Session, tenant_id: int, usage_type: str) -> int:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    value = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.usage_type == usage_type,
            UsageEvent.created_at >= start,
        )
    )
    return int(value or 0)


def active_plan(db: Session, tenant_id: int) -> Plan:
    subscription = db.scalar(
        select(Subscription).where(Subscription.tenant_id == tenant_id).order_by(Subscription.id.desc())
    )
    if subscription is None:
        plan = db.scalar(select(Plan).where(Plan.code == 'free'))
        if plan is None:
            raise RuntimeError('free plan is not seeded')
        return plan
    if subscription.status in {'past_due', 'unpaid', 'incomplete', 'incomplete_expired', 'paused'}:
        raise PaymentRequired(subscription.status)
    if subscription.status == 'canceled' and subscription.plan.code != 'free':
        raise PaymentRequired(subscription.status)
    return subscription.plan


def record_billable_usage(db: Session, tenant: Tenant, request: GenerateRequest, idempotency_key: str, settings: Settings) -> GenerateResponse:
    locked_tenant = db.scalar(select(Tenant).where(Tenant.id == tenant.id).with_for_update())
    if locked_tenant is None or not locked_tenant.active:
        raise ValueError('tenant is inactive or missing')

    incoming_hash = request_hash(request)
    existing = db.scalar(select(UsageEvent).where(
        UsageEvent.tenant_id == tenant.id,
        UsageEvent.idempotency_key == idempotency_key,
    ))
    if existing:
        if existing.request_hash != incoming_hash:
            raise IdempotencyConflict('idempotency key was already used with a different request payload')
        return GenerateResponse.model_validate(json.loads(existing.response_json))

    plan = active_plan(db, tenant.id)
    usage_units = request.quantity if request.usage_type == 'api_call' else request.token_quota_units
    used = current_usage(db, tenant.id, request.usage_type)
    limit = plan.monthly_api_call_limit if request.usage_type == 'api_call' else plan.monthly_ai_token_limit

    if used + usage_units > limit:
        raise QuotaExceeded(request.usage_type, used, usage_units, limit)

    cost = calculate_cost(
        settings,
        request.usage_type,
        quantity=request.quantity,
        input_tokens=request.input_tokens,
        cached_input_tokens=request.cached_input_tokens,
        output_tokens=request.output_tokens,
        reasoning_tokens=request.reasoning_tokens,
    )
    if request.usage_type == 'ai_tokens' and cost > settings.max_ai_cost_micro_usd_per_request:
        raise BudgetExceeded(cost, settings.max_ai_cost_micro_usd_per_request)

    provisional = GenerateResponse(
        event_id=0,
        tenant=tenant.external_key,
        usage_type=request.usage_type,
        recorded_quantity=usage_units,
        cost_micro_usd=cost,
        status='recorded',
    )
    event = UsageEvent(
        tenant_id=tenant.id,
        usage_type=request.usage_type,
        quantity=usage_units,
        idempotency_key=idempotency_key,
        request_hash=incoming_hash,
        response_json='{}',
        response_status=200,
        input_tokens=request.input_tokens,
        cached_input_tokens=request.cached_input_tokens,
        output_tokens=request.output_tokens,
        reasoning_tokens=request.reasoning_tokens,
        cost_micro_usd=cost,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(select(UsageEvent).where(
            UsageEvent.tenant_id == tenant.id,
            UsageEvent.idempotency_key == idempotency_key,
        ))
        if winner is None:
            raise
        if winner.request_hash != incoming_hash:
            raise IdempotencyConflict('idempotency key was already used with a different request payload')
        return GenerateResponse.model_validate(json.loads(winner.response_json))

    response = provisional.model_copy(update={'event_id': event.id})
    event.response_json = response.model_dump_json()
    db.commit()
    return response
