from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKeyConstraint, Index, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class ImeProducer(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "ime_producers"

    producer_code: int = Field(primary_key=True)
    name: str = Field(max_length=250, index=True)
    enabled: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False, index=True))
    synced_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )


class ImeProduct(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "ime_products"

    producer_code: int = Field(primary_key=True)
    symbol: str = Field(primary_key=True, max_length=120)
    goods_name: str = Field(max_length=500)
    unit: str = Field(default="", max_length=40)
    currency: str = Field(default="", max_length=40)
    category: str | None = Field(default=None, max_length=80)
    last_trade_date: date | None = Field(default=None, index=True)
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    __table_args__ = (
        ForeignKeyConstraint(["producer_code"], ["ime_producers.producer_code"]),
        UniqueConstraint("producer_code", "symbol", name="uq_ime_product_producer_symbol"),
        Index("idx_ime_products_producer_name", "producer_code", "goods_name"),
    )
