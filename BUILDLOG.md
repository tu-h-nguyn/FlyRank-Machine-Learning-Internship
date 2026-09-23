# BUILDLOG

## AI-assisted build

This project was built with AI assistance, as permitted by the capstone brief. The implementation was reviewed against the published acceptance probes and exercised with automated tests.

### Where AI helped

- Proposed FastAPI + SQLAlchemy + PostgreSQL layering.
- Drafted the data model and Alembic migration.
- Drafted idempotency, quota, pricing, Stripe webhook and worker services.
- Generated the first-pass tests and documentation scaffolding.

### Human review / corrections applied

- Kept idempotency at the database boundary with unique tenant + key enforcement.
- Added a request hash so an idempotency-key payload mismatch returns 409.
- Locked the tenant row before quota calculation on PostgreSQL.
- Stored money as integer micro-USD and kept token categories separate.
- Billed reasoning tokens at the output-token rate.
- Verified the raw webhook body before JSON decoding.
- Added unique Stripe event IDs for replay protection.
- Added retry + failure persistence to the background usage-alert job.
- Corrected the Docker Compose healthcheck and environment YAML syntax before packaging.

### Known external verification limit

A dedicated public repository must be created separately for the final portal submission. The code/artifacts are complete; the current GitHub staging copy is inside an existing repository solely as a handoff location. Docker/PostgreSQL and live Stripe CLI execution were not available in the build environment.
