import os

os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'
os.environ['BACKGROUND_WORKER_ENABLED'] = 'false'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Plan, Subscription, Tenant


@pytest.fixture()
def db_session():
    engine = create_engine(
        'sqlite+pysqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()

    free = Plan(
        code='free',
        name='Free',
        monthly_api_call_limit=3,
        monthly_ai_token_limit=100_000_000,
        monthly_price_cents=0,
    )
    pro = Plan(
        code='pro',
        name='Pro',
        monthly_api_call_limit=10,
        monthly_ai_token_limit=100_000_000,
        monthly_price_cents=2000,
    )
    db.add_all([free, pro])
    db.flush()

    tenant = Tenant(external_key='tenant-a', name='Tenant A')
    tenant2 = Tenant(external_key='tenant-b', name='Tenant B')
    db.add_all([tenant, tenant2])
    db.flush()
    db.add_all([
        Subscription(tenant_id=tenant.id, plan_id=free.id, status='active'),
        Subscription(tenant_id=tenant2.id, plan_id=free.id, status='active'),
    ])
    db.commit()

    yield db
    db.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr('app.api.routes.settings.stripe_webhook_secret', 'whsec_test')
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
