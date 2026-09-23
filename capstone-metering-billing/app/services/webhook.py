from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, ProcessedWebhook, Subscription, Tenant


def unix_to_dt(value):
    return datetime.fromtimestamp(value, tz=timezone.utc) if value else None


def handle_event(db: Session, event: dict) -> bool:
    event_id = event.get('id')
    event_type = event.get('type', '')
    if not event_id:
        raise ValueError('missing Stripe event id')

    exists = db.scalar(select(ProcessedWebhook).where(ProcessedWebhook.stripe_event_id == event_id))
    if exists:
        return False

    obj = event.get('data', {}).get('object', {})
    tenant_key = obj.get('metadata', {}).get('tenant_key')
    tenant = db.scalar(select(Tenant).where(Tenant.external_key == tenant_key)) if tenant_key else None

    if event_type == 'checkout.session.completed':
        if tenant is None:
            tenant_key = obj.get('client_reference_id')
            tenant = db.scalar(select(Tenant).where(Tenant.external_key == tenant_key)) if tenant_key else None
        if tenant is None:
            raise ValueError('checkout event does not identify a known tenant')
        subscription_id = obj.get('subscription')
        customer_id = obj.get('customer')
        pro = db.scalar(select(Plan).where(Plan.code == 'pro'))
        if pro is None:
            raise ValueError('pro plan is not seeded')
        subscription = db.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant.id).order_by(Subscription.id.desc())
        )
        if subscription is None:
            subscription = Subscription(tenant_id=tenant.id, plan_id=pro.id)
            db.add(subscription)
        else:
            subscription.plan_id = pro.id
        subscription.status = 'active'
        subscription.stripe_customer_id = customer_id
        subscription.stripe_subscription_id = subscription_id

    elif event_type == 'customer.subscription.updated':
        subscription_id = obj.get('id')
        subscription = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == subscription_id))
        if subscription is None and tenant is not None:
            free = db.scalar(select(Plan).where(Plan.code == 'free'))
            subscription = Subscription(tenant_id=tenant.id, plan_id=free.id)
            db.add(subscription)
        if subscription is None:
            raise ValueError('subscription update does not match a known subscription')
        stripe_status = obj.get('status', 'active')
        subscription.status = stripe_status
        subscription.stripe_customer_id = obj.get('customer') or subscription.stripe_customer_id
        subscription.current_period_start = unix_to_dt(obj.get('current_period_start'))
        subscription.current_period_end = unix_to_dt(obj.get('current_period_end'))
        pro = db.scalar(select(Plan).where(Plan.code == 'pro'))
        free = db.scalar(select(Plan).where(Plan.code == 'free'))
        subscription.plan_id = pro.id if stripe_status in {'active', 'trialing'} else free.id

    elif event_type == 'customer.subscription.deleted':
        subscription_id = obj.get('id')
        subscription = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == subscription_id))
        if subscription:
            free = db.scalar(select(Plan).where(Plan.code == 'free'))
            subscription.plan_id = free.id
            subscription.status = 'canceled'

    else:
        db.add(ProcessedWebhook(stripe_event_id=event_id, event_type=event_type))
        db.commit()
        return True

    db.add(ProcessedWebhook(stripe_event_id=event_id, event_type=event_type))
    db.commit()
    return True
