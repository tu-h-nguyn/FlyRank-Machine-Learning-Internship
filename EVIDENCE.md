# EVIDENCE

The deterministic transcript below was generated locally with PYTHONPATH=. python scripts/evidence_smoke.py on 2026-09-23. The automated suite also passes with 15 passed.

## 1. Metering — exactly once under retry

Test: tests/test_metering.py::test_idempotency_creates_one_event_and_mirrors_response

~~~text
P1 idempotency: 200 200 True events= 1
~~~

The database also enforces unique (tenant_id, idempotency_key).

## 2. Quotas — explicit boundary

~~~text
P2 quota boundary: fill= 200 next= 429 {'detail': {'message': 'api_call quota exceeded', 'used': 3, 'requested': 1, 'limit': 3}}
~~~

The test fixture uses a three-call Free limit for deterministic boundary testing. Production seed uses the required 1,000-call Free limit.

Rule: used + requested <= limit is allowed; exceeding the limit returns 429 with used, requested and limit.

## 3. Cost calculation — cached and reasoning rules

~~~text
P3 pricing: 200 725000 expected=725000
~~~

For 1M fresh input, 1M cached input, 1M output and 1M reasoning:
~~~text
100000 + 25000 + 300000 + 300000 = 725000 micro-USD = $0.725000
~~~

Reasoning is billed as output; money storage is integer micro-USD.

## 4. Stripe integration — verification and replay

~~~text
P4 forged webhook: 400 api_limit_after= 3
P4 replay webhook: {'status': 'processed', 'event_id': 'evt-valid'} {'status': 'duplicate', 'event_id': 'evt-valid'} api_limit= 10
~~~

The forged signature is rejected before mutation. A signed checkout event flips the tenant to Pro; replay of the same event ID is ignored.

Live Stripe Checkout and Stripe CLI forwarding were not executed in this environment because no Stripe CLI/test credentials were available. The code is configured for Stripe test mode only.

## 5. Persistence and tenant isolation

~~~text
P6 tenant isolation: 3 0
~~~

Alembic migration 0001 creates plans, tenants, subscriptions, usage_events, processed_webhooks, usage_alerts and job_failures, with usage indexes and tenant/key uniqueness.

## 6. Boundary validation and AI budget guard

~~~text
P5 boundary validation: 422 Value error, ai_tokens requires at least one token category
P5 budget guard: 400 5000001 5000000
~~~

Invalid input is rejected with a 4xx. An AI request above the configured 5,000,000 micro-USD budget is rejected before persistence.

## 7. Background job, retry and failure evidence

~~~text
P7 background alert initial scan: created= 2
P7 background alert once-only: first_scan= 1 second_scan= 0
P7 worker failure: attempts= 3 persisted_attempts= 3 message= synthetic worker failure
~~~

The worker scans the 80% and 100% thresholds, persists each threshold once per tenant/type/month, retries failures, writes job_failures after the configured retry count and emits a CRITICAL log.

## Automated test result

~~~text
pytest -q
15 passed
~~~

## Secrets

.env is git-ignored. .env.example contains placeholders only. No live credential is included.

## Verification limits

Docker/PostgreSQL and real Stripe CLI execution were unavailable in the build environment. Those paths are configured and documented but not claimed as live-verified.
