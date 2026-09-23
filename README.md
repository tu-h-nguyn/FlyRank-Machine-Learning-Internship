# FlyRank Usage Metering & Billing Engine

A bounded multi-tenant FastAPI backend that meters API calls and simulated AI tokens, enforces Free/Pro monthly quotas, calculates integer-only usage cost, and synchronizes Stripe test-mode subscriptions through verified, idempotent webhooks.

## Architecture

~~~text
Client
  |
  +--> POST /generate --X-Tenant-Key + Idempotency-Key-->
  |       |
  |       +--> idempotency lookup
  |       +--> tenant lock
  |       +--> quota check
  |       +--> integer cost calculation
  |       +--> usage_events INSERT
  |       +--> 200 / 409 / 429 / 402
  |
  +--> GET /usage --> monthly rollup --> used / limit / cost
  |
  +--> POST /billing/checkout --> Stripe Test Checkout
  |
  +<-- Stripe signed webhook -- POST /webhooks/stripe
               |
               +--> raw-body signature verification
               +--> event-id deduplication
               +--> subscription / plan sync

Background worker every minute
  --> usage thresholds --> usage_alerts
  --> retries --> job_failures + CRITICAL log
~~~

## Plans

| Plan | API calls/month | AI tokens/month | Monthly subscription |
|---|---:|---:|---:|
| Free | 1,000 | 100,000 | $0 |
| Pro | 10,000 | 1,000,000 | $20 |

The brief fixes the Free limits and allows a higher Pro limit to be chosen and documented.

## Pinned cost rules

Money is stored as integer micro-USD. One micro-USD is 0.000001 USD.

- API call: 1,000 micro-USD per call.
- Fresh input: 100,000 micro-USD per 1M tokens.
- Cached input: 25,000 micro-USD per 1M tokens.
- Output: 300,000 micro-USD per 1M tokens.
- Reasoning tokens are billed at the output rate.
- AI request budget guard: 5,000,000 micro-USD per request.
- Each token category uses integer ceiling division before the category totals are summed.

## Run locally

1. Configure:
~~~bash
cp .env.example .env
~~~

2. Start:
~~~bash
docker compose up --build
~~~

The API starts on http://localhost:8000 after migration and seed.

3. Health:
~~~bash
curl http://localhost:8000/health
~~~

4. Meter a call:
~~~bash
curl -X POST http://localhost:8000/generate   -H 'Content-Type: application/json'   -H 'X-Tenant-Key: demo-free'   -H 'Idempotency-Key: demo-001'   -d '{"usage_type":"api_call","quantity":1}'
~~~

5. Inspect usage:
~~~bash
curl 'http://localhost:8000/usage?tenant_key=demo-free'
~~~

## Stripe test mode

Checkout endpoint:
~~~text
POST /billing/checkout?tenant_key=demo-free
~~~

The endpoint refuses non-test Stripe keys. For local delivery:
~~~bash
stripe listen --forward-to localhost:8000/webhooks/stripe
~~~

Use Stripe test cards only. Never put Stripe credentials in Git.

## Tests

~~~bash
pytest -q
PYTHONPATH=. python scripts/evidence_smoke.py
~~~

The suite covers idempotency, key conflicts, quota boundaries, tenant isolation, AI pricing, webhook verification/replay, subscription lifecycle, validation, budget guard, and background worker retry/failure behavior.

## Submission pack

README.md, capstone.yaml, EVIDENCE.md, BUILDLOG.md, .env.example, and DESIGN.md are included.

## Limitations

This is intentionally small. It does not implement real payments, invoicing, proration, overage billing, or a live model call. Stripe is test-mode only. The background scanner runs in the API process rather than a separate queue. The demo tenant key is the authentication boundary and is not a complete identity system.

## Verification note

The deterministic local suite passed 15 tests and the evidence smoke script passed all published probes. Docker/PostgreSQL and live Stripe CLI execution were not available in the build environment, so those external integrations are documented but not claimed as live-verified.
