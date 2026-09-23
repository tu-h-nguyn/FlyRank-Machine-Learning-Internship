# One-page design

## Problem

A small multi-tenant SaaS backend must answer three questions reliably: how much a tenant used, whether it is inside plan quotas, and what the measured usage costs. Stripe test-mode subscriptions provide payment truth.

## Data model

- plans: Free/Pro quotas and subscription prices.
- tenants: isolated customer organizations keyed by external_key.
- subscriptions: Stripe-backed plan/status per tenant.
- usage_events: immutable billable activity plus request hash, stored response, token breakdown and integer micro-USD cost.
- processed_webhooks: unique Stripe event IDs for replay protection.
- usage_alerts: once-per-month 80%/100% threshold records.
- job_failures: permanent background-worker failure evidence.

## Metering contract

POST /generate requires X-Tenant-Key, Idempotency-Key and a JSON body. The service locks the tenant row, checks an existing idempotency key, hashes the request payload, validates monthly quota, computes integer cost, inserts one usage_events row and returns the stored response. A repeated key with the same payload mirrors the original response; the same key with a different payload returns 409.

## Quota semantics

A request is allowed when used + requested <= limit. The first request that would exceed the limit is rejected with 429 and a structured explanation. Lapsed payment states return 402.

## Billing semantics

API calls use a fixed integer micro-USD price. Fresh input, cached input and output-equivalent tokens have separate integer rates. Reasoning tokens are added to output tokens for billing. Monthly /usage rolls all stored event costs into one integer micro-USD total.

## Stripe path

Checkout is created only with a test-mode key. The session carries tenant_key in metadata. /webhooks/stripe verifies the raw request signature before JSON decoding. checkout.session.completed, customer.subscription.updated and customer.subscription.deleted are applied once per unique event ID.

## Layering

HTTP routes -> service layer -> SQLAlchemy models. Stripe HTTP is isolated in stripe_service.py. The background scanner is detached from request handling.

## Explicit non-goals

No invoicing, proration, real payments, overage charging, model invocation, or public webhook tunnel.
