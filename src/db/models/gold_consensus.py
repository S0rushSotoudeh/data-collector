import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, func
from sqlmodel import Field, SQLModel


class GoldKalmanDataset(SQLModel, table=True):
    __tablename__ = "gold_kalman_datasets"
    dataset_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    status: str = "uploading"
    manifest: dict = Field(sa_column=Column(JSON, nullable=False))
    sha256: str = ""
    row_count: int = 0
    error: str = ""
    created_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))


class GoldKalmanCalibration(SQLModel, table=True):
    __tablename__ = "gold_kalman_calibrations"
    calibration_id: uuid.UUID = Field(primary_key=True)
    run_id: uuid.UUID = Field(index=True)
    session_open: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    method: str
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
