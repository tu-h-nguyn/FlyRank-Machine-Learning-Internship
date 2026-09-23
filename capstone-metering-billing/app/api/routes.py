import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Plan, Subscription, Tenant, UsageEvent
from app.schemas.api import CheckoutResponse, GenerateRequest, GenerateResponse, UsageSummary
from app.services.metering import (
    BudgetExceeded,
    IdempotencyConflict,
    PaymentRequired,
    QuotaExceeded,
    record_billable_usage,
)
from app.services.pricing import micro_usd_to_decimal_string
from app.services.stripe_service import StripeError, create_checkout_session, verify_signature
from app.services.webhook import handle_event

router = APIRouter()
settings = get_settings()


def get_tenant(db: Session, tenant_key: str) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.external_key == tenant_key))
    if tenant is None:
        raise HTTPException(status_code=404, detail='unknown tenant')
    return tenant


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.post('/generate', response_model=GenerateResponse)
def generate(
    request: GenerateRequest,
    tenant_key: str = Header(..., alias='X-Tenant-Key'),
    idempotency_key: str = Header(..., alias='Idempotency-Key'),
    db: Session = Depends(get_db),
):
    if len(idempotency_key) > 255:
        raise HTTPException(status_code=400, detail='Idempotency-Key too long')
    tenant = get_tenant(db, tenant_key)
    try:
        return record_billable_usage(db, tenant, request, idempotency_key, settings)
    except QuotaExceeded as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                'message': f'{exc.usage_type} quota exceeded',
                'used': exc.used,
                'requested': exc.requested,
                'limit': exc.limit,
            },
            headers={'Retry-After': '3600'},
        ) from exc
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaymentRequired as exc:
        db.rollback()
        raise HTTPException(
            status_code=402,
            detail={'message': 'upgrade or payment required', 'subscription_status': exc.status},
        ) from exc
    except BudgetExceeded as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                'message': 'AI request cost exceeds per-request budget',
                'cost_micro_usd': exc.cost_micro_usd,
                'budget_micro_usd': exc.limit_micro_usd,
            },
        ) from exc


@router.get('/usage', response_model=UsageSummary)
def usage(tenant_key: str, db: Session = Depends(get_db)):
    tenant = get_tenant(db, tenant_key)
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    plan = db.scalar(
        select(Plan)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.tenant_id == tenant.id,
            Subscription.status.in_(['active', 'trialing']),
        )
        .order_by(Subscription.id.desc())
    )
    if plan is None:
        plan = db.scalar(select(Plan).where(Plan.code == 'free'))

    api_used = int(db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.tenant_id == tenant.id,
        UsageEvent.usage_type == 'api_call',
        UsageEvent.created_at >= start,
    )) or 0)
    token_used = int(db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.tenant_id == tenant.id,
        UsageEvent.usage_type == 'ai_tokens',
        UsageEvent.created_at >= start,
    )) or 0)
    cost = int(db.scalar(select(func.coalesce(func.sum(UsageEvent.cost_micro_usd), 0)).where(
        UsageEvent.tenant_id == tenant.id,
        UsageEvent.created_at >= start,
    )) or 0)

    return UsageSummary(
        tenant=tenant.external_key,
        month=start.strftime('%Y-%m'),
        api_calls_used=api_used,
        api_calls_limit=plan.monthly_api_call_limit,
        ai_tokens_used=token_used,
        ai_tokens_limit=plan.monthly_ai_token_limit,
        cost_micro_usd=cost,
        cost_usd=micro_usd_to_decimal_string(cost),
    )


@router.post('/billing/checkout', response_model=CheckoutResponse)
async def billing_checkout(tenant_key: str, db: Session = Depends(get_db)):
    tenant = get_tenant(db, tenant_key)
    try:
        result = await create_checkout_session(settings, tenant.external_key)
    except StripeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CheckoutResponse(checkout_url=result['url'], session_id=result['id'])


@router.post('/webhooks/stripe')
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get('Stripe-Signature', '')
    try:
        verify_signature(payload, signature, settings.stripe_webhook_secret, settings.webhook_tolerance_seconds)
        event = json.loads(payload)
    except (StripeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail='invalid Stripe webhook') from exc

    try:
        processed = handle_event(db, event)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {'status': 'processed' if processed else 'duplicate', 'event_id': event['id']}
