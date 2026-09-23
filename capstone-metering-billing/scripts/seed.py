from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Plan, Subscription, Tenant


def main():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        free = db.scalar(select(Plan).where(Plan.code == 'free'))
        if free is None:
            free = Plan(code='free', name='Free', monthly_api_call_limit=1_000, monthly_ai_token_limit=100_000, monthly_price_cents=0)
            db.add(free)
        pro = db.scalar(select(Plan).where(Plan.code == 'pro'))
        if pro is None:
            pro = Plan(code='pro', name='Pro', monthly_api_call_limit=10_000, monthly_ai_token_limit=1_000_000, monthly_price_cents=2_000)
            db.add(pro)
        db.flush()
        for key, name in [('demo-free', 'Demo Free Tenant'), ('demo-pro', 'Demo Pro Tenant')]:
            tenant = db.scalar(select(Tenant).where(Tenant.external_key == key))
            if tenant is None:
                tenant = Tenant(external_key=key, name=name)
                db.add(tenant)
                db.flush()
            sub = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id).order_by(Subscription.id.desc()))
            if sub is None:
                sub = Subscription(tenant_id=tenant.id, plan_id=free.id if key == 'demo-free' else pro.id, status='active')
                db.add(sub)
        db.commit()
        print('Seed complete: demo-free (Free), demo-pro (Pro)')
    finally:
        db.close()


if __name__ == '__main__':
    main()
