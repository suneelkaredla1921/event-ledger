import logging
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, Response

from gateway import metrics
from gateway.account_client import AccountServiceError, account_client
from gateway.database import EventRecord, db
from gateway.logging_config import trace_id_var
from gateway.schemas import ErrorDetail, EventRequest, EventResponse, HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _event_to_response(record: EventRecord) -> EventResponse:
    return EventResponse(
        eventId=record.event_id,
        accountId=record.account_id,
        type=record.type,
        amount=record.amount,
        currency=record.currency,
        eventTimestamp=record.event_timestamp,
        metadata=record.metadata,
    )


def _ensure_trace(x_trace_id: str | None) -> str:
    trace = x_trace_id or str(uuid.uuid4())
    trace_id_var.set(trace)
    return trace


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    metrics.record_request("GET /health")
    from gateway.config import get_settings

    connected = db.is_connected()
    status = "ok" if connected else "degraded"
    return HealthResponse(
        status=status,
        service="event-gateway",
        databaseConnected=connected,
        accountServiceUrl=get_settings().account_service_url,
        metrics=metrics.snapshot(),
    )


@router.post(
    "/events",
    response_model=EventResponse,
    summary="Submit a transaction event",
    description=(
        "Validates the event, applies the transaction on Account Service, and stores "
        "the event locally. Duplicate submissions with the same `eventId` are idempotent."
    ),
    responses={
        201: {
            "description": "Created — first successful submission for this eventId.",
            "model": EventResponse,
        },
        200: {
            "description": "OK — duplicate eventId; returns the original stored event.",
            "model": EventResponse,
        },
        422: {
            "description": "Unprocessable Entity — validation failed.",
            "model": ErrorDetail,
        },
        503: {
            "description": "Service Unavailable — Account Service unreachable after retries.",
            "model": ErrorDetail,
        },
    },
)
def post_event(
    body: EventRequest,
    response: Response,
    request: Request,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-ID"),
) -> EventResponse:
    metrics.record_request("POST /events")
    trace = _ensure_trace(x_trace_id)
    response.headers["X-Trace-ID"] = trace
    logger.info("Received event %s for account %s", body.eventId, body.accountId)

    existing = db.get_event(body.eventId)
    if existing is not None:
        logger.info("Duplicate event %s, returning stored record", body.eventId)
        response.status_code = 200
        return _event_to_response(existing)

    tx_payload = {
        "eventId": body.eventId,
        "type": body.type,
        "amount": body.amount,
        "currency": body.currency,
        "eventTimestamp": body.eventTimestamp,
        "metadata": body.metadata,
    }

    try:
        account_client.apply_transaction(body.accountId, tx_payload, trace)
    except AccountServiceError as exc:
        metrics.record_error("POST /events")
        if exc.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail="Account Service is temporarily unavailable. Please retry later.",
            ) from exc
        raise HTTPException(
            status_code=exc.status_code or 502,
            detail=str(exc),
        ) from exc

    record = EventRecord(
        event_id=body.eventId,
        account_id=body.accountId,
        type=body.type,
        amount=body.amount,
        currency=body.currency,
        event_timestamp=body.eventTimestamp,
        metadata=body.metadata,
    )
    db.save_event(record)
    response.status_code = 201
    return _event_to_response(record)


@router.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: str) -> EventResponse:
    metrics.record_request("GET /events/{id}")
    record = db.get_event(event_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return _event_to_response(record)


@router.get("/events", response_model=list[EventResponse])
def list_events(account: str) -> list[EventResponse]:
    metrics.record_request("GET /events")
    records = db.list_by_account(account)
    return [_event_to_response(r) for r in records]
