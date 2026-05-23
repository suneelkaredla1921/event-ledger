import logging
import time
from typing import Any

import httpx

from gateway.config import get_settings

logger = logging.getLogger(__name__)


class AccountServiceError(Exception):
    """Raised when Account Service is unavailable after retries."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AccountServiceClient:
    """Synchronous REST client with timeout and exponential backoff retry."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.account_service_url).rstrip("/")

    def apply_transaction(
        self,
        account_id: str,
        payload: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        settings = get_settings()
        url = f"{self.base_url}/accounts/{account_id}/transactions"
        headers = {"X-Trace-ID": trace_id, "Content-Type": "application/json"}
        last_error: Exception | None = None

        for attempt in range(settings.account_max_retries):
            try:
                with httpx.Client(timeout=settings.account_request_timeout) as client:
                    response = client.post(url, json=payload, headers=headers)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "server error",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 400:
                    raise AccountServiceError(
                        response.text,
                        status_code=response.status_code,
                    )
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < settings.account_max_retries - 1:
                    delay = settings.account_backoff_base * (2**attempt)
                    logger.warning(
                        "Account Service call failed (attempt %s/%s), retrying in %.2fs: %s",
                        attempt + 1,
                        settings.account_max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Account Service unavailable after %s attempts: %s",
                        settings.account_max_retries,
                        exc,
                    )

        raise AccountServiceError(
            f"Account Service unavailable: {last_error}",
            status_code=503,
        ) from last_error

    def get_balance(self, account_id: str, trace_id: str) -> dict[str, Any]:
        settings = get_settings()
        url = f"{self.base_url}/accounts/{account_id}/balance"
        headers = {"X-Trace-ID": trace_id}
        try:
            with httpx.Client(timeout=settings.account_request_timeout) as client:
                response = client.get(url, headers=headers)
            if response.status_code == 404:
                raise AccountServiceError(response.json().get("detail", "Not found"), 404)
            if response.status_code >= 500 or response.status_code == 503:
                raise AccountServiceError("Account Service unavailable", 503)
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AccountServiceError(
                "Account Service unavailable",
                status_code=503,
            ) from exc


account_client = AccountServiceClient()
