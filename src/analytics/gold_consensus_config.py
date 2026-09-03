"""Immutable policy and explicit historical-session metadata for gold replay."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

MODEL_VERSION = "gold-consensus-v1"


class SessionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    open: AwareDatetime
    close: AwareDatetime
    eligible_symbols: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounds(self):
        if self.close <= self.open or (self.close - self.open).total_seconds() > 86400:
            raise ValueError("session must have positive duration of at most one day")
        if len(set(self.eligible_symbols)) != len(self.eligible_symbols):
            raise ValueError("duplicate eligible symbols")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=160)
    source_reference: str = Field(min_length=1, max_length=2000)
    calendar_reference: str = Field(min_length=1, max_length=2000)
    eligibility_reference: str = Field(min_length=1, max_length=2000)
    phase_reference: str = Field(min_length=1, max_length=2000)
    clock: Literal["historical_arrival", "exchange_time", "synthetic"]
    price_unit: Literal["IRR"] = "IRR"
    sessions: list[SessionSpec] = Field(min_length=1, max_length=366)

    @model_validator(mode="after")
    def ordered_sessions(self):
        for a, b in zip(self.sessions, self.sessions[1:]):
            if a.close > b.open:
                raise ValueError("sessions must be chronological and nonoverlapping")
        return self


class GoldKalmanRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    dataset_id: UUID
    symbols: list[str] = Field(min_length=3, max_length=100)
    history_from: AwareDatetime
    validation_from: AwareDatetime
    validation_to: AwareDatetime
    test_from: AwareDatetime
    test_to: AwareDatetime
    mode: Literal["validation", "test"] = "validation"
    validation_run_id: UUID | None = None
    calibration_lookback_sessions: int = Field(default=3, ge=1, le=60)
    min_calibration_observations: int = Field(default=60, ge=3)
    kalman_half_life_seconds: float = Field(default=30, gt=0)
    warmup_seconds: float = Field(default=120, ge=0)
    analysis_horizon_seconds: float = Field(default=60, gt=0)
    max_quote_age: float = Field(default=10, gt=0)
    z_alert: float = Field(default=2, gt=0)
    k: int = Field(default=3, ge=1)
    model_version: Literal["gold-consensus-v1"] = MODEL_VERSION

    @model_validator(mode="after")
    def validate_policy(self):
        if not self.history_from < self.validation_from < self.validation_to <= self.test_from < self.test_to:
            raise ValueError("require history < validation_from < validation_to <= test_from < test_to")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("duplicate symbols")
        if self.mode == "test" and self.validation_run_id is None:
            raise ValueError("final testing requires a completed validation_run_id")
        return self

    def policy_hash(self) -> str:
        policy = self.model_dump(mode="json", exclude={"mode", "validation_run_id"})
        policy["symbols"] = sorted(policy["symbols"])
        return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()

    def evaluation_bounds(self) -> tuple[datetime, datetime]:
        return (self.validation_from, self.validation_to) if self.mode == "validation" else (self.test_from, self.test_to)
