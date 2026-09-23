from typing import Literal

from pydantic import BaseModel, Field, field_validator

UsageType = Literal['api_call', 'ai_tokens']


class GenerateRequest(BaseModel):
    usage_type: UsageType
    quantity: int = Field(default=1, ge=1)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @field_validator('quantity')
    @classmethod
    def quantity_for_api(cls, value: int) -> int:
        if value > 100_000_000:
            raise ValueError('quantity is too large')
        return value

    def model_post_init(self, __context) -> None:
        if self.usage_type == 'api_call':
            if any([self.input_tokens, self.cached_input_tokens, self.output_tokens, self.reasoning_tokens]):
                raise ValueError('token fields must be zero for api_call')
        else:
            token_total = self.input_tokens + self.cached_input_tokens + self.output_tokens + self.reasoning_tokens
            if token_total <= 0:
                raise ValueError('ai_tokens requires at least one token category')
            if self.quantity != 1:
                raise ValueError('ai_tokens quantity must be 1; token fields define usage')

    @property
    def token_quota_units(self) -> int:
        return self.input_tokens + self.cached_input_tokens + self.output_tokens + self.reasoning_tokens


class GenerateResponse(BaseModel):
    event_id: int
    tenant: str
    usage_type: UsageType
    recorded_quantity: int
    cost_micro_usd: int
    status: str


class UsageSummary(BaseModel):
    tenant: str
    month: str
    api_calls_used: int
    api_calls_limit: int
    ai_tokens_used: int
    ai_tokens_limit: int
    cost_micro_usd: int
    cost_usd: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class ErrorResponse(BaseModel):
    detail: str
