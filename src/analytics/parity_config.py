from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.analytics.parity import FEE_PRESETS, Fees, margin_per_share


class ParityRunConfig(BaseModel):
    underlying_instrument_code: str
    call_instrument_code: str
    put_instrument_code: str
    start_date: date
    end_date: date
    start_time: time = time(8, 30)
    end_time: time = time(12, 30)
    interval_seconds: int = Field(30, ge=1, le=3600)
    max_quote_age_seconds: int = Field(60, ge=0, le=86400)
    expiry_cutoff: time = time(12, 30)
    multiplier: int = Field(..., gt=0)
    tick_size: float | None = Field(None, gt=0)
    margin_value: float = Field(0, ge=0)
    margin_unit: Literal["per_share", "per_contract", "percent", "basis_points"] = "per_share"
    funding_source: Literal["curve", "manual", "mixed"] = "curve"
    manual_borrowing_rate: float | None = Field(None, ge=-1, le=5)
    borrowing_spread: float | None = Field(None, ge=-1, le=5)
    stock_fee_category: Literal["tse_stock", "ifb_stock", "tse_equity_etf"] = "tse_stock"
    option_fee_category: Literal["tse_option", "ifb_option"] = "tse_option"
    stock_buy_fee: float | None = Field(None, ge=0, lt=1)
    stock_sell_fee: float | None = Field(None, ge=0, lt=1)
    call_buy_fee: float | None = Field(None, ge=0, lt=1)
    call_sell_fee: float | None = Field(None, ge=0, lt=1)
    put_buy_fee: float | None = Field(None, ge=0, lt=1)
    put_sell_fee: float | None = Field(None, ge=0, lt=1)

    @model_validator(mode="after")
    def validate_range_and_funding(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if self.start_time > self.end_time:
            raise ValueError("start_time must not be after end_time")
        if self.funding_source == "manual" and self.manual_borrowing_rate is None:
            raise ValueError("manual funding requires a borrowing rate")
        return self

    def effective_fees(self) -> Fees:
        stock = FEE_PRESETS[self.stock_fee_category]
        option = FEE_PRESETS[self.option_fee_category]
        return Fees(
            stock_buy=stock["buy"] if self.stock_buy_fee is None else self.stock_buy_fee,
            stock_sell=stock["sell"] if self.stock_sell_fee is None else self.stock_sell_fee,
            call_buy=option["buy"] if self.call_buy_fee is None else self.call_buy_fee,
            call_sell=option["sell"] if self.call_sell_fee is None else self.call_sell_fee,
            put_buy=option["buy"] if self.put_buy_fee is None else self.put_buy_fee,
            put_sell=option["sell"] if self.put_sell_fee is None else self.put_sell_fee,
        )

    def converted_margin(self, strike: float) -> float:
        return margin_per_share(self.margin_value, self.margin_unit, strike, self.multiplier)
