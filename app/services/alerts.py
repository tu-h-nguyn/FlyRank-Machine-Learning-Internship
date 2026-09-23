from datetime import datetime, timezone
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobFailure, Plan, Subscription, Tenant, UsageAlert
from app.services.metering import current_usage

logger = logging.getLogger(__name__)
THRESHOLDS = (80, 100)


def run_usage_alert_scan(db: Session) -> int:
    month_key = datetime.now(timezone.utc).strftime('%Y-%m')
    created = 0
    tenants = db.scalars(select(Tenant).where(Tenant.active.is_(True))).all()
    for tenant in tenants:
        plan = db.scalar(select(Plan).join(Subscription, Subscription.plan_id == Plan.id).where(
            Subscription.tenant_id == tenant.id,
            Subscription.status.in_(['active', 'trialing']),
        ).order_by(Subscription.id.desc()))
        if plan is None:
            plan = db.scalar(select(Plan).where(Plan.code == 'free'))
        for usage_type, limit in (
            ('api_call', plan.monthly_api_call_limit),
            ('ai_tokens', plan.monthly_ai_token_limit),
        ):
            used = current_usage(db, tenant.id, usage_type)
            if limit <= 0:
                continue
            pct = (used * 100) // limit
            for threshold in THRESHOLDS:
                if pct >= threshold:
                    exists = db.scalar(select(UsageAlert).where(
                        UsageAlert.tenant_id == tenant.id,
                        UsageAlert.usage_type == usage_type,
                        UsageAlert.threshold_pct == threshold,
                        UsageAlert.month_key == month_key,
                    ))
                    if exists is None:
                        db.add(UsageAlert(
                            tenant_id=tenant.id,
                            usage_type=usage_type,
                            threshold_pct=threshold,
                            month_key=month_key,
                        ))
                        logger.warning(
                            'usage_alert tenant=%s type=%s threshold=%s%% used=%s limit=%s',
                            tenant.external_key, usage_type, threshold, used, limit,
                        )
                        created += 1
    db.commit()
    return created


def run_with_retry(session_factory, retry_count: int = 3) -> None:
    last_error = None
    for attempt in range(1, retry_count + 1):
        db = session_factory()
        try:
            run_usage_alert_scan(db)
            db.close()
            return
        except Exception as exc:
            last_error = exc
            db.rollback()
            db.close()
            logger.exception('background job failure attempt=%s/%s', attempt, retry_count)
    db = session_factory()
    db.add(JobFailure(job_name='usage-alert-scan', error_message=str(last_error), attempts=retry_count))
    db.commit()
    db.close()
    logger.critical('background job failed after retries: %s', last_error)
