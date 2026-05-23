import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, Response

from account import metrics
from account.database import TransactionRecord, db
from account.logging_config import trace_id_var
from account.schemas import (
    AccountResponse,
    BalanceResponse,
    HealthResponse,
    TransactionRequest,
    TransactionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _set_trace(trace_id: str | None) -> str:
    resolved = trace_id or str(uuid.uuid4())
    trace_id_var.set(resolved)
    return resolved


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    metrics.record_request("GET /health")
    connected = db.is_connected()
    status = "ok" if connected else "degraded"
    return HealthResponse(
        status=status,
        service="account-service",
        databaseConnected=connected,
        metrics=metrics.snapshot(),
    )


@router.post(
    "/accounts/{account_id}/transactions",
    response_model=TransactionResponse,
)
def post_transaction(
    account_id: str,
    body: TransactionRequest,
    response: Response,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-ID"),
) -> TransactionResponse:
    metrics.record_request("POST /accounts/{accountId}/transactions")
    trace = _set_trace(x_trace_id)
    logger.info("Applying transaction for account %s event %s", account_id, body.eventId)

    tx = TransactionRecord(
        event_id=body.eventId,
        type=body.type,
        amount=body.amount,
        currency=body.currency,
        event_timestamp=body.eventTimestamp,
        metadata=body.metadata,
    )

    existing = db.get_transaction(account_id, body.eventId)
    if existing is not None:
        balance = db.compute_balance(account_id) or 0.0
        response.status_code = 200
        logger.info(
            "Duplicate transaction event %s for account %s traceId=%s",
            body.eventId,
            account_id,
            trace,
        )
        return TransactionResponse(
            eventId=existing.event_id,
            accountId=account_id,
            type=existing.type,
            amount=existing.amount,
            currency=existing.currency,
            eventTimestamp=existing.event_timestamp,
            metadata=existing.metadata,
            balance=balance,
        )

    db.add_transaction(account_id, tx)
    balance = db.compute_balance(account_id) or 0.0
    response.status_code = 201
    return TransactionResponse(
        eventId=tx.event_id,
        accountId=account_id,
        type=tx.type,
        amount=tx.amount,
        currency=tx.currency,
        eventTimestamp=tx.event_timestamp,
        metadata=tx.metadata,
        balance=balance,
    )


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
def get_balance(
    account_id: str,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-ID"),
) -> BalanceResponse:
    metrics.record_request("GET /accounts/{accountId}/balance")
    _set_trace(x_trace_id)

    account = db.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    balance = db.compute_balance(account_id) or 0.0
    return BalanceResponse(
        accountId=account_id,
        balance=balance,
        currency=account.currency,
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-ID"),
) -> AccountResponse:
    metrics.record_request("GET /accounts/{accountId}")
    _set_trace(x_trace_id)

    account = db.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")

    balance = db.compute_balance(account_id) or 0.0
    transactions = [
        TransactionResponse(
            eventId=tx.event_id,
            accountId=account_id,
            type=tx.type,
            amount=tx.amount,
            currency=tx.currency,
            eventTimestamp=tx.event_timestamp,
            metadata=tx.metadata,
            balance=balance,
        )
        for tx in db.list_transactions(account_id)
    ]
    return AccountResponse(
        accountId=account_id,
        balance=balance,
        currency=account.currency,
        transactions=transactions,
    )
