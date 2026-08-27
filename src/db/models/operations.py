from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, DateTime, Index, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlmodel import Field, SQLModel


class OperationRun(SQLModel, table=True):  # type: ignore[call-arg]
    """Canonical lifecycle record for every meaningful background operation."""

    __tablename__ = "operation_runs"

    run_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    family: str = Field(max_length=40, index=True)
    run_type: str = Field(max_length=96, index=True)
    status: str = Field(default="queued", max_length=24, index=True)
    trigger: str = Field(default="manual", max_length=24, index=True)
    celery_task_id: str | None = Field(default=None, max_length=80, index=True)
    target: str | None = Field(default=None, max_length=160, index=True)
    start_date: date | None = Field(default=None, index=True)
    end_date: date | None = Field(default=None, index=True)
    config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    result: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    progress_current: int = Field(default=0, ge=0, sa_column=Column(BigInteger, nullable=False))
    progress_total: int = Field(default=0, ge=0, sa_column=Column(BigInteger, nullable=False))
    output_count: int = Field(default=0, ge=0, sa_column=Column(BigInteger, nullable=False))
    warning_count: int = Field(default=0, ge=0, sa_column=Column(BigInteger, nullable=False))
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by: str | None = Field(default=None, max_length=120)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        Index("idx_operation_runs_family_created", "family", "created_at"),
        Index("idx_operation_runs_type_dates", "run_type", "start_date", "end_date"),
    )


class OptionPricingConvention(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "option_pricing_conventions"

    convention_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=120, unique=True)
    contract_family: str = Field(default="tsetmc_equity_option", max_length=80, index=True)
    effective_from: date = Field(default=date(2016, 12, 18))
    effective_to: date | None = None
    exercise_style: str = Field(default="European", max_length=24)
    settlement_style: str = Field(default="cash_and_physical", max_length=40)
    multiplier: int = Field(default=1000, gt=0)
    tick_size: float = Field(default=1.0, gt=0)
    price_unit: str = Field(default="IRR", max_length=24)
    black76_compatible: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, default=True)
    )
    reference_source: str = Field(
        default="Tehran Stock Exchange option contract notices (https://www.tse.ir/)",
        max_length=500,
    )
    approved: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
    approver: str | None = Field(default=None, max_length=120)
    approved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        Index("idx_pricing_convention_effective", "contract_family", "effective_from", "effective_to"),
    )


class OptionFeeSchedule(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "option_fee_schedules"

    fee_schedule_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    market: str = Field(max_length=8, index=True)
    effective_from: date = Field(index=True)
    effective_to: date | None = Field(default=None, index=True)
    buy_rate: Decimal = Field(sa_column=Column(Numeric(12, 8), nullable=False))
    sell_rate: Decimal = Field(sa_column=Column(Numeric(12, 8), nullable=False))
    settlement_cost_per_contract: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(18, 4), nullable=True)
    )
    source: str = Field(max_length=500)
    notes: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        UniqueConstraint("market", "effective_from", name="uq_option_fee_market_effective_from"),
        CheckConstraint("market IN ('tse', 'ifb')", name="ck_option_fee_market"),
        CheckConstraint("buy_rate >= 0 AND buy_rate < 1", name="ck_option_fee_buy_rate"),
        CheckConstraint("sell_rate >= 0 AND sell_rate < 1", name="ck_option_fee_sell_rate"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_option_fee_effective_range",
        ),
        CheckConstraint(
            "settlement_cost_per_contract IS NULL OR settlement_cost_per_contract >= 0",
            name="ck_option_fee_settlement_cost",
        ),
        Index("idx_option_fee_market_effective", "market", "effective_from", "effective_to"),
    )
