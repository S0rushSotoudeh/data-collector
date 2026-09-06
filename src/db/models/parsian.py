from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlmodel import Field, SQLModel


class ParsianCredential(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "parsian_credentials"

    id: int = Field(default=1, primary_key=True)
    token_ciphertext: str = Field(sa_column=Column(Text, nullable=False))
    token_fingerprint: str = Field(sa_column=Column(String(16), nullable=False))
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    validated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
