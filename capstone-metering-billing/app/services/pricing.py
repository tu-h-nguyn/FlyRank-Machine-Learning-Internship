from decimal import Decimal

from app.config import Settings


def micro_usd_for_million_tokens(tokens: int, rate_micro_usd_per_million: int) -> int:
    if tokens <= 0:
        return 0
    return (tokens * rate_micro_usd_per_million + 999_999) // 1_000_000


def calculate_cost(settings: Settings, usage_type: str, *, quantity: int = 1,
                   input_tokens: int = 0, cached_input_tokens: int = 0,
                   output_tokens: int = 0, reasoning_tokens: int = 0) -> int:
    if usage_type == 'api_call':
        return quantity * settings.api_call_cost_micro_usd
    output_equivalent = output_tokens + reasoning_tokens
    return (
        micro_usd_for_million_tokens(input_tokens, settings.input_cost_micro_usd_per_million)
        + micro_usd_for_million_tokens(cached_input_tokens, settings.cached_input_cost_micro_usd_per_million)
        + micro_usd_for_million_tokens(output_equivalent, settings.output_cost_micro_usd_per_million)
    )


def micro_usd_to_decimal_string(value: int) -> str:
    amount = Decimal(value) / Decimal(1_000_000)
    return f'{amount:.6f}'
