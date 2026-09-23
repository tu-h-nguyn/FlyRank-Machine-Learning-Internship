import hashlib
import hmac
import time

import httpx

from app.config import Settings


class StripeError(RuntimeError):
    pass


def verify_signature(payload: bytes, signature_header: str, secret: str, tolerance_seconds: int = 300) -> None:
    if not secret or not signature_header:
        raise StripeError('missing webhook secret or signature')
    parts = [p.strip() for p in signature_header.split(',')]
    timestamp = next((p.split('=', 1)[1] for p in parts if p.startswith('t=') and '=' in p), None)
    signatures = [p.split('=', 1)[1] for p in parts if p.startswith('v1=') and '=' in p]
    if not timestamp or not signatures:
        raise StripeError('invalid webhook signature format')
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise StripeError('invalid webhook timestamp') from exc
    if abs(time.time() - ts) > tolerance_seconds:
        raise StripeError('webhook timestamp outside tolerance')
    signed = f'{timestamp}.'.encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise StripeError('invalid webhook signature')


async def create_checkout_session(settings: Settings, tenant_external_key: str) -> dict:
    if not settings.stripe_secret_key:
        raise StripeError('STRIPE_SECRET_KEY is not configured')
    if not settings.stripe_secret_key.startswith('sk_test_'):
        raise StripeError('only Stripe test-mode keys (sk_test_) are allowed')
    data = {
        'mode': 'subscription',
        'success_url': settings.stripe_success_url,
        'cancel_url': settings.stripe_cancel_url,
        'client_reference_id': tenant_external_key,
        'metadata[tenant_key]': tenant_external_key,
        'line_items[0][price_data][currency]': settings.stripe_price_currency,
        'line_items[0][price_data][unit_amount]': str(settings.stripe_pro_monthly_cents),
        'line_items[0][price_data][recurring][interval]': 'month',
        'line_items[0][price_data][product_data][name]': 'FlyRank Pro',
        'line_items[0][quantity]': '1',
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            'https://api.stripe.com/v1/checkout/sessions',
            data=data,
            headers={'Authorization': f'Bearer {settings.stripe_secret_key}'},
        )
    if response.status_code >= 400:
        raise StripeError(f'Stripe Checkout failed: {response.text[:500]}')
    return response.json()
