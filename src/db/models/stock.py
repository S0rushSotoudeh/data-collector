from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, DateTime, func, Index
from sqlmodel import SQLModel, Field


class StockInstrument(SQLModel, table=True):  # type: ignore
    __tablename__ = "stock_instruments"

    instrument_code: str = Field(primary_key=True, max_length=20)
    name_fa: str | None = Field(default=None, max_length=200)
    name_en: str | None = Field(default=None, max_length=100)
    symbol: str | None = Field(default=None, max_length=50)
    isin: str | None = Field(default=None, max_length=30)
    instrument_id: str | None = Field(default=None, max_length=50, unique=True)
    total_issued: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    base_volume: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
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
    avg_daily_volume_5y: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    last_trade_date: date | None = Field(default=None)
    status: str | None = Field(default=None, max_length=20)
    listing_date: date | None = Field(default=None)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        Index("idx_stock_symbol", "symbol"),
        Index("idx_stock_status", "status"),
        Index("idx_stock_security_type", "security_type_code"),
    )
