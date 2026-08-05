from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class BoxSpreadRunConfig(BaseModel):
    trade_date: date
    underlying_instrument_code: str
    expiry_date: date
    lower_strike: float = Field(..., gt=0)
    upper_strike: float = Field(..., gt=0)
    target_box_count: int = Field(1, ge=1, le=1_000_000)
    session_start: time = time(8, 30)
    session_end: time = time(12, 30)
    interval_seconds: int = Field(30, ge=1, le=3600)
    max_quote_age_seconds: int = Field(60, ge=0, le=3600)
    max_cross_leg_skew_seconds: int = Field(2, ge=0, le=1800)
    expiry_cutoff: time = time(12, 30)
    pricing_convention_id: UUID
    minimum_ytm_spread_bps: float = Field(0, ge=0, le=100_000)
    funding_source: Literal["curve", "manual", "mixed"] = "curve"
    manual_funding_rate: float | None = Field(None, ge=-1, le=5)
    funding_spread: float | None = Field(None, ge=-1, le=5)
    option_fee_category: Literal["tse_option", "ifb_option"] = "tse_option"
    option_buy_fee: float | None = Field(None, ge=0, lt=1)
    option_sell_fee: float | None = Field(None, ge=0, lt=1)
    settlement_cost_per_contract: float = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_run(self):
        if self.lower_strike >= self.upper_strike:
            raise ValueError("lower_strike must be below upper_strike")
        if self.trade_date > self.expiry_date:
            raise ValueError("trade_date must not be after expiry_date")
        if self.session_start > self.session_end:
            raise ValueError("session_start must not be after session_end")
        if self.funding_source == "manual" and self.manual_funding_rate is None:
            raise ValueError("manual funding requires manual_funding_rate")
        return self

    def effective_option_fees(self) -> tuple[float, float]:
        from src.analytics.parity import FEE_PRESETS

        preset = FEE_PRESETS[self.option_fee_category]
        return (
            preset["buy"] if self.option_buy_fee is None else self.option_buy_fee,
            preset["sell"] if self.option_sell_fee is None else self.option_sell_fee,
        )
