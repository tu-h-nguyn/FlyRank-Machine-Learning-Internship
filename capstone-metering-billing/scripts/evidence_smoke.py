"""Deterministic acceptance transcript for the capstone evidence pack."""
import hashlib
import hmac
import json
import logging
import os
import time

os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_test'
os.environ['BACKGROUND_WORKER_ENABLED'] = 'false'

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Plan, Subscription, Tenant, UsageEvent
from app.services.alerts import run_with_retry
import app.services.alerts as alerts

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('app.services.alerts').setLevel(logging.WARNING)


def sign(payload: bytes, secret='whsec_test') -> str:
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), f'{timestamp}.'.encode() + payload, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={digest}'


def make_event(event_id, event_type, obj):
    return {'id': event_id, 'type': event_type, 'data': {'object': obj}}


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
db.add_all([
    Tenant(external_key='tenant-a', name='Tenant A'),
    Tenant(external_key='tenant-b', name='Tenant B'),
])
db.flush()
for tenant_id, plan in [(1, free.id), (2, free.id)]:
    db.add(Subscription(tenant_id=tenant_id, plan_id=plan, status='active'))
db.commit()


def override_get_db():
    yield db


app.dependency_overrides[get_db] = override_get_db

with TestClient(app) as client:
    headers = {'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'idem-evidence'}
    body = {'usage_type': 'api_call', 'quantity': 1}
    first = client.post('/generate', json=body, headers=headers)
    second = client.post('/generate', json=body, headers=headers)
    count = db.execute(text('select count(*) from usage_events where tenant_id=1')).scalar_one()
    print('P1 idempotency:', first.status_code, second.status_code, first.json() == second.json(), 'events=', count)

    boundary = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 2},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'boundary-fill'},
    )
    next_request = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'boundary-next'},
    )
    print('P2 quota boundary:', 'fill=', boundary.status_code, 'next=', next_request.status_code, next_request.json())

    price_body = {
        'usage_type': 'ai_tokens',
        'quantity': 1,
        'input_tokens': 1_000_000,
        'cached_input_tokens': 1_000_000,
        'output_tokens': 1_000_000,
        'reasoning_tokens': 1_000_000,
    }
    price = client.post(
        '/generate',
        json=price_body,
        headers={'X-Tenant-Key': 'tenant-b', 'Idempotency-Key': 'pricing-evidence'},
    )
    print('P3 pricing:', price.status_code, price.json()['cost_micro_usd'], 'expected=725000')

    forged_event = make_event('evt-forged', 'checkout.session.completed', {
        'client_reference_id': 'tenant-b',
        'metadata': {'tenant_key': 'tenant-b'},
        'customer': 'cus-forged',
        'subscription': 'sub-forged',
    })
    forged_payload = json.dumps(forged_event).encode()
    forged = client.post(
        '/webhooks/stripe',
        content=forged_payload,
        headers={'Stripe-Signature': 't=1,v1=bad'},
    )
    unchanged = client.get('/usage', params={'tenant_key': 'tenant-b'}).json()['api_calls_limit']
    print('P4 forged webhook:', forged.status_code, 'api_limit_after=', unchanged)

    checkout_event = make_event('evt-valid', 'checkout.session.completed', {
        'client_reference_id': 'tenant-b',
        'metadata': {'tenant_key': 'tenant-b'},
        'customer': 'cus-valid',
        'subscription': 'sub-valid',
    })
    checkout_payload = json.dumps(checkout_event).encode()
    signed_headers = {'Stripe-Signature': sign(checkout_payload)}
    first_webhook = client.post('/webhooks/stripe', content=checkout_payload, headers=signed_headers)
    replay_webhook = client.post('/webhooks/stripe', content=checkout_payload, headers=signed_headers)
    upgraded = client.get('/usage', params={'tenant_key': 'tenant-b'}).json()['api_calls_limit']
    print('P4 replay webhook:', first_webhook.json(), replay_webhook.json(), 'api_limit=', upgraded)

    invalid = client.post(
        '/generate',
        json={'usage_type': 'ai_tokens', 'quantity': 2},
        headers={'X-Tenant-Key': 'tenant-b', 'Idempotency-Key': 'bad-input'},
    )
    print('P5 boundary validation:', invalid.status_code, invalid.json()['detail'][0]['msg'])

    budget = client.post(
        '/generate',
        json={
            'usage_type': 'ai_tokens',
            'quantity': 1,
            'input_tokens': 50_000_001,
        },
        headers={'X-Tenant-Key': 'tenant-b', 'Idempotency-Key': 'budget-evidence'},
    )
    print(
        'P5 budget guard:',
        budget.status_code,
        budget.json()['detail']['cost_micro_usd'],
        budget.json()['detail']['budget_micro_usd'],
    )

    usage_a = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    usage_b = client.get('/usage', params={'tenant_key': 'tenant-b'}).json()
    print('P6 tenant isolation:', usage_a['api_calls_used'], usage_b['api_calls_used'])

initial_scan = alerts.run_usage_alert_scan(db)
print('P7 background alert initial scan:', 'created=', initial_scan)

db.add(UsageEvent(
    tenant_id=2,
    usage_type='api_call',
    quantity=8,
    idempotency_key='worker-evidence',
    request_hash='h',
    response_json='{}',
    response_status=200,
    input_tokens=0,
    cached_input_tokens=0,
    output_tokens=0,
    reasoning_tokens=0,
    cost_micro_usd=8000,
))
db.commit()

created_once = alerts.run_usage_alert_scan(db)
created_again = alerts.run_usage_alert_scan(db)
print('P7 background alert once-only:', 'first_scan=', created_once, 'second_scan=', created_again)

original = alerts.run_usage_alert_scan
attempts = {'count': 0}


def failing(db):
    attempts['count'] += 1
    raise RuntimeError('synthetic worker failure')


alerts.run_usage_alert_scan = failing
run_with_retry(lambda: db, retry_count=3)
alerts.run_usage_alert_scan = original
failure = db.execute(text('select attempts, error_message from job_failures order by id desc limit 1')).one()
print(
    'P7 worker failure:',
    'attempts=', attempts['count'],
    'persisted_attempts=', failure[0],
    'message=', failure[1],
)

app.dependency_overrides.clear()
db.close()
