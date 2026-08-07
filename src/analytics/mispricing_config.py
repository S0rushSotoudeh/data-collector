from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class OptionMispricingRunConfig(BaseModel):
    trade_date: date
    start_time: time = time(8, 30)
    end_time: time = time(12, 30)
    interval_seconds: int = Field(30, ge=1, le=3600)
    max_quote_age_seconds: int = Field(60, ge=1, le=86400)
    expiry_cutoff: time = time(12, 30)
    pricing_convention_id: UUID
    manual_funding_rate: float | None = Field(None, ge=-1, le=5)

    @model_validator(mode="after")
    def validate_session(self):
        if self.start_time > self.end_time:
            raise ValueError("start_time must not be after end_time")
        return self
