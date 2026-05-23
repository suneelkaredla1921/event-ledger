from collections import defaultdict
from threading import Lock

_lock = Lock()
_request_counts: dict[str, int] = defaultdict(int)
_error_counts: dict[str, int] = defaultdict(int)


def record_request(endpoint: str) -> None:
    with _lock:
        _request_counts[endpoint] += 1


def record_error(endpoint: str) -> None:
    with _lock:
        _error_counts[endpoint] += 1


def snapshot() -> dict:
    with _lock:
        return {
            "requestCountByEndpoint": dict(_request_counts),
            "errorCountByEndpoint": dict(_error_counts),
        }


def reset() -> None:
    with _lock:
        _request_counts.clear()
        _error_counts.clear()
