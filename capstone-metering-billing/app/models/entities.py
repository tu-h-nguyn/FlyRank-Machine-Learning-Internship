from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Plan(Base):
    __tablename__ = 'plans'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_api_call_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_ai_token_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscriptions: Mapped[list['Subscription']] = relationship(back_populates='plan')


class Tenant(Base):
    __tablename__ = 'tenants'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    subscriptions: Mapped[list['Subscription']] = relationship(back_populates='tenant', cascade='all, delete-orphan')
    usage_events: Mapped[list['UsageEvent']] = relationship(back_populates='tenant', cascade='all, delete-orphan')


class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey('plans.id'), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='active')
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    tenant: Mapped[Tenant] = relationship(back_populates='subscriptions')
    plan: Mapped[Plan] = relationship(back_populates='subscriptions')


class UsageEvent(Base):
    __tablename__ = 'usage_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_micro_usd: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tenant: Mapped[Tenant] = relationship(back_populates='usage_events')
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_usage_tenant_idempotency'),
        Index('ix_usage_tenant_created', 'tenant_id', 'created_at'),
        Index('ix_usage_tenant_type_created', 'tenant_id', 'usage_type', 'created_at'),
    )


class ProcessedWebhook(Base):
    __tablename__ = 'processed_webhooks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UsageAlert(Base):
    __tablename__ = 'usage_alerts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint('tenant_id', 'usage_type', 'threshold_pct', 'month_key', name='uq_usage_alert_once'),
    )


class JobFailure(Base):
    __tablename__ = 'job_failures'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
