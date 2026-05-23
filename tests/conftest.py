import pytest
from fastapi.testclient import TestClient

from account.database import configure_database as configure_account_db
from account.metrics import reset as reset_account_metrics
from gateway.account_client import AccountServiceError
from gateway.database import configure_database as configure_gateway_db
from gateway.metrics import reset as reset_gateway_metrics
import gateway.routes as gateway_routes


@pytest.fixture(autouse=True)
def reset_databases(tmp_path, monkeypatch):
    gateway_url = f"sqlite:///{(tmp_path / 'gateway.db').as_posix()}"
    account_url = f"sqlite:///{(tmp_path / 'account.db').as_posix()}"
    monkeypatch.setenv("GATEWAY_DATABASE_URL", gateway_url)
    monkeypatch.setenv("ACCOUNT_DATABASE_URL", account_url)

    configure_gateway_db(gateway_url, reset=True)
    configure_account_db(account_url, reset=True)

    from account.config import get_settings as get_account_settings
    from gateway.config import get_settings as get_gateway_settings

    get_gateway_settings.cache_clear()
    get_account_settings.cache_clear()

    reset_account_metrics()
    reset_gateway_metrics()
    yield


@pytest.fixture
def account_client():
    from account.main import app

    return TestClient(app)


@pytest.fixture
def gateway_client(account_client):
    from gateway.main import app

    class InlineAccountClient:
        def apply_transaction(self, account_id: str, payload: dict, trace_id: str) -> dict:
            response = account_client.post(
                f"/accounts/{account_id}/transactions",
                json=payload,
                headers={"X-Trace-ID": trace_id},
            )
            if response.status_code >= 500:
                raise AccountServiceError("Account Service unavailable", status_code=503)
            if response.status_code >= 400:
                raise AccountServiceError(response.text, status_code=response.status_code)
            return response.json()

        def get_balance(self, account_id: str, trace_id: str) -> dict:
            response = account_client.get(
                f"/accounts/{account_id}/balance",
                headers={"X-Trace-ID": trace_id},
            )
            if response.status_code >= 500:
                raise AccountServiceError("Account Service unavailable", status_code=503)
            if response.status_code == 404:
                raise AccountServiceError(response.json().get("detail", "Not found"), 404)
            response.raise_for_status()
            return response.json()

    gateway_routes.account_client = InlineAccountClient()
    return TestClient(app)


@pytest.fixture
def sample_event():
    return {
        "eventId": "evt-001",
        "accountId": "acct-123",
        "type": "CREDIT",
        "amount": 150.00,
        "currency": "USD",
        "eventTimestamp": "2026-05-15T14:02:11Z",
        "metadata": {"source": "mainframe-batch", "batchId": "B-9042"},
    }
