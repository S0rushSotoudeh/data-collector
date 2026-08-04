from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class IVSurfaceRunConfig(BaseModel):
    underlying_instrument_code: str
    start_date: date
    end_date: date
    session_start: time = time(8, 30)
    session_end: time = time(12, 30)
    interval_seconds: Literal[10, 30]
    max_quote_age_seconds: int = Field(60, ge=1, le=3600)
    pricing_convention_id: UUID
    manual_funding_rate: float | None = Field(None, ge=-1, le=5)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        if self.session_start > self.session_end:
            raise ValueError("session_start must not be after session_end")
        return self
