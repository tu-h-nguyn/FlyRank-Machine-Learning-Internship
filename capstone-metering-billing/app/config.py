from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'FlyRank Usage Metering & Billing Engine'
    environment: str = 'development'
    database_url: str = 'sqlite:///./app.db'
    stripe_secret_key: str = ''
    stripe_webhook_secret: str = ''
    stripe_success_url: str = 'http://localhost:8000/billing/success'
    stripe_cancel_url: str = 'http://localhost:8000/billing/cancel'
    stripe_price_currency: str = 'usd'
    stripe_pro_monthly_cents: int = 2000
    webhook_tolerance_seconds: int = 300
    worker_interval_seconds: int = 60
    worker_retry_count: int = 3
    background_worker_enabled: bool = True
    api_call_cost_micro_usd: int = 1000
    input_cost_micro_usd_per_million: int = 100_000
    cached_input_cost_micro_usd_per_million: int = 25_000
    output_cost_micro_usd_per_million: int = 300_000
    max_ai_cost_micro_usd_per_request: int = 5_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
