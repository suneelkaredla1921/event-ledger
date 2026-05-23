import httpx
from fastapi.testclient import TestClient

from gateway.account_client import AccountServiceClient, AccountServiceError
import gateway.routes as gateway_routes


def test_post_events_returns_503_when_account_service_unavailable(
    gateway_client, sample_event
):
    class FailingClient:
        def apply_transaction(self, account_id: str, payload: dict, trace_id: str):
            raise AccountServiceError("Account Service unavailable", status_code=503)

    gateway_routes.account_client = FailingClient()
    response = gateway_client.post("/events", json=sample_event)
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()

    assert gateway_client.get("/events/evt-001").status_code == 404
    assert gateway_client.get("/events", params={"account": "acct-123"}).json() == []


def test_balance_query_clear_error_when_account_unreachable(monkeypatch):
    monkeypatch.setenv("ACCOUNT_REQUEST_TIMEOUT", "0.3")
    from gateway.config import get_settings

    get_settings.cache_clear()
    client = AccountServiceClient(base_url="http://127.0.0.1:1")
    try:
        client.get_balance("acct-123", "trace-test")
        raised = False
    except AccountServiceError as exc:
        raised = True
        assert exc.status_code == 503
        assert "unavailable" in str(exc).lower()
    assert raised


def test_retry_with_backoff_then_succeed(sample_event, monkeypatch):
    from gateway.account_client import account_client
    from gateway.main import app

    gateway_routes.account_client = account_client
    attempts = {"count": 0}

    class FlakyHttp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise httpx.ConnectError("connection refused")
            request = httpx.Request("POST", url)
            return httpx.Response(
                201,
                json={
                    "eventId": json["eventId"],
                    "accountId": "acct-123",
                    "type": json["type"],
                    "amount": json["amount"],
                    "currency": json["currency"],
                    "eventTimestamp": json["eventTimestamp"],
                    "metadata": json.get("metadata"),
                    "balance": 150.0,
                },
                request=request,
            )

    monkeypatch.setattr("gateway.account_client.httpx.Client", FlakyHttp)
    monkeypatch.setenv("ACCOUNT_MAX_RETRIES", "3")
    monkeypatch.setenv("ACCOUNT_BACKOFF_BASE", "0")
    from gateway.config import get_settings

    get_settings.cache_clear()

    client = TestClient(app)
    response = client.post("/events", json=sample_event)
    assert response.status_code == 201
    assert attempts["count"] == 2
