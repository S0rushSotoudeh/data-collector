from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, func, Index
from sqlmodel import SQLModel, Field


class BondInstrument(SQLModel, table=True):  # type: ignore
    __tablename__ = "bond_instruments"

    instrument_code: str = Field(primary_key=True, max_length=20)
    name_fa: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=100)
    symbol: str | None = Field(default=None, max_length=50)
    isin: str | None = Field(default=None, max_length=30, unique=True)
    instrument_id: str | None = Field(default=None, max_length=50, unique=True)
    total_issued: int | None = Field(default=None)
    base_volume: int | None = Field(default=None)
    market_code: int | None = Field(default=None)
    market_name: str | None = Field(default=None, max_length=100)
    segment_code: str | None = Field(default=None, max_length=10)
    segment_name: str | None = Field(default=None, max_length=100)
    security_type_code: str | None = Field(default=None, max_length=10)
    security_type_name: str | None = Field(default=None, max_length=100)
    price_ceiling: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    price_floor: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    low_52w: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    high_52w: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    low_yearly: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    high_yearly: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    avg_daily_volume_5y: int | None = Field(default=None)
    last_trade_date: date | None = Field(default=None)
    status: str | None = Field(default=None, max_length=20)
    maturity_date: date | None = Field(default=None)
    listing_date: date | None = Field(default=None)
    created_at: datetime | None = Field(
        default=None,
        init=False,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        init=False,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        Index("idx_bond_symbol", "symbol"),
        Index("idx_bond_status", "status"),
        Index("idx_bond_maturity", "maturity_date"),
    )