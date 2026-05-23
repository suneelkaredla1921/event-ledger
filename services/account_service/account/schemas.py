from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TransactionRequest(BaseModel):
    eventId: str = Field(..., min_length=1)
    type: Literal["CREDIT", "DEBIT"]
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=1)
    eventTimestamp: str = Field(..., min_length=1)
    metadata: dict[str, Any] | None = None

    @field_validator("eventTimestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        normalized = value.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("eventTimestamp must be a valid ISO 8601 datetime") from exc
        return value


class TransactionResponse(BaseModel):
    eventId: str
    accountId: str
    type: str
    amount: float
    currency: str
    eventTimestamp: str
    metadata: dict[str, Any] | None = None
    balance: float


class BalanceResponse(BaseModel):
    accountId: str
    balance: float
    currency: str | None = None


class AccountResponse(BaseModel):
    accountId: str
    balance: float
    currency: str | None = None
    transactions: list[TransactionResponse]


class HealthResponse(BaseModel):
    status: str
    service: str
    databaseConnected: bool
    metrics: dict[str, Any]
