import hashlib
import hmac
import json
import time


def sign(payload: bytes, secret='whsec_test') -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), f'{timestamp}.'.encode() + payload, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={signature}'


def test_idempotency_creates_one_event_and_mirrors_response(client, db_session):
    headers = {'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'same-key'}
    payload = {'usage_type': 'api_call', 'quantity': 1}
    first = client.post('/generate', json=payload, headers=headers)
    second = client.post('/generate', json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    rows = db_session.execute(__import__('sqlalchemy').text('select count(*) from usage_events')).scalar_one()
    assert rows == 1


def test_idempotency_conflict_is_409(client):
    headers = {'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'same-key'}
    assert client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers=headers,
    ).status_code == 200

    conflict = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 2},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_quota_boundary_and_next_request(client):
    headers = {'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'k-1'}
    assert client.post('/generate', json={'usage_type': 'api_call', 'quantity': 3}, headers=headers).status_code == 200

    rejected = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers={**headers, 'Idempotency-Key': 'k-2'},
    )
    assert rejected.status_code == 429
    assert rejected.json()['detail']['limit'] == 3


def test_tenant_isolation(client):
    client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'a'},
    )
    usage_a = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    usage_b = client.get('/usage', params={'tenant_key': 'tenant-b'}).json()

    assert usage_a['api_calls_used'] == 1
    assert usage_b['api_calls_used'] == 0


def test_pricing_rules_and_reasoning_billed_as_output(client):
    payload = {
        'usage_type': 'ai_tokens',
        'quantity': 1,
        'input_tokens': 1_000_000,
        'cached_input_tokens': 1_000_000,
        'output_tokens': 1_000_000,
        'reasoning_tokens': 1_000_000,
    }
    response = client.post(
        '/generate',
        json=payload,
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'price-1'},
    )
    assert response.status_code == 200
    assert response.json()['cost_micro_usd'] == 725_000


def test_forged_webhook_returns_400_and_does_not_change_plan(client):
    event = {
        'id': 'evt_1',
        'type': 'checkout.session.completed',
        'data': {'object': {
            'client_reference_id': 'tenant-a',
            'metadata': {'tenant_key': 'tenant-a'},
            'customer': 'cus_1',
            'subscription': 'sub_1',
        }},
    }
    payload = json.dumps(event).encode()
    forged = client.post('/webhooks/stripe', content=payload, headers={'Stripe-Signature': 't=1,v1=bad'})

    assert forged.status_code == 400
    usage = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    assert usage['api_calls_limit'] == 3


def test_valid_checkout_webhook_is_deduplicated(client):
    event = {
        'id': 'evt_2',
        'type': 'checkout.session.completed',
        'data': {'object': {
            'client_reference_id': 'tenant-a',
            'metadata': {'tenant_key': 'tenant-a'},
            'customer': 'cus_2',
            'subscription': 'sub_2',
        }},
    }
    payload = json.dumps(event).encode()
    headers = {'Stripe-Signature': sign(payload)}

    first = client.post('/webhooks/stripe', content=payload, headers=headers)
    second = client.post('/webhooks/stripe', content=payload, headers=headers)

    assert first.json()['status'] == 'processed'
    assert second.json()['status'] == 'duplicate'
    usage = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    assert usage['api_calls_limit'] == 10


def test_invalid_request_returns_422(client):
    response = client.post(
        '/generate',
        json={'usage_type': 'ai_tokens', 'quantity': 2},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'bad-1'},
    )
    assert response.status_code == 422


def test_ai_budget_guard(client):
    payload = {
        'usage_type': 'ai_tokens',
        'quantity': 1,
        'input_tokens': 50_000_001,
    }
    response = client.post(
        '/generate',
        json=payload,
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'budget-1'},
    )
    assert response.status_code == 400
    assert response.json()['detail']['budget_micro_usd'] == 5_000_000


def test_payment_required_for_lapsed_subscription(client, db_session):
    sub = db_session.query(__import__('app.models', fromlist=['Subscription']).Subscription).filter_by(tenant_id=1).one()
    sub.status = 'past_due'
    db_session.commit()

    response = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'past-due-1'},
    )
    assert response.status_code == 402


def test_subscription_updated_changes_plan_and_status(client):
    event = {
        'id': 'evt_3',
        'type': 'customer.subscription.updated',
        'data': {'object': {
            'id': 'sub_2',
            'customer': 'cus_2',
            'status': 'past_due',
            'metadata': {'tenant_key': 'tenant-a'},
        }},
    }
    payload = json.dumps(event).encode()

    response = client.post(
        '/webhooks/stripe',
        content=payload,
        headers={'Stripe-Signature': sign(payload)},
    )
    assert response.status_code == 200
    usage = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    assert usage['api_calls_limit'] == 3

    blocked = client.post(
        '/generate',
        json={'usage_type': 'api_call', 'quantity': 1},
        headers={'X-Tenant-Key': 'tenant-a', 'Idempotency-Key': 'lapsed-1'},
    )
    assert blocked.status_code == 402


def test_subscription_deleted_moves_tenant_to_free(client):
    checkout = {
        'id': 'evt_4',
        'type': 'checkout.session.completed',
        'data': {'object': {
            'client_reference_id': 'tenant-a',
            'metadata': {'tenant_key': 'tenant-a'},
            'customer': 'cus_4',
            'subscription': 'sub_4',
        }},
    }
    checkout_payload = json.dumps(checkout).encode()
    assert client.post(
        '/webhooks/stripe',
        content=checkout_payload,
        headers={'Stripe-Signature': sign(checkout_payload)},
    ).status_code == 200

    deleted = {
        'id': 'evt_5',
        'type': 'customer.subscription.deleted',
        'data': {'object': {'id': 'sub_4', 'customer': 'cus_4'}},
    }
    deleted_payload = json.dumps(deleted).encode()
    response = client.post(
        '/webhooks/stripe',
        content=deleted_payload,
        headers={'Stripe-Signature': sign(deleted_payload)},
    )
    assert response.status_code == 200

    usage = client.get('/usage', params={'tenant_key': 'tenant-a'}).json()
    assert usage['api_calls_limit'] == 3


def test_unsupported_webhook_is_acknowledged_and_deduplicated(client):
    event = {'id': 'evt_unsupported', 'type': 'customer.created', 'data': {'object': {}}}
    payload = json.dumps(event).encode()
    headers = {'Stripe-Signature': sign(payload)}

    first = client.post('/webhooks/stripe', content=payload, headers=headers)
    second = client.post('/webhooks/stripe', content=payload, headers=headers)

    assert first.status_code == 200 and first.json()['status'] == 'processed'
    assert second.status_code == 200 and second.json()['status'] == 'duplicate'
