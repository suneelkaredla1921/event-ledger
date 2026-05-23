# Event Ledger — Implementation Documentation

This document maps the take-home problem statement to what was implemented, how to run the system, and how to confirm each goal is satisfied.

---

## Tech stack

| Component | Choice | Role |
|-----------|--------|------|
| **Python 3.12** | Language | Both microservices |
| **FastAPI** | Web framework | REST APIs, routing, OpenAPI docs |
| **Uvicorn** | ASGI server | Runs each service process |
| **Pydantic v2** | Validation | Request/response models, field rules, ISO 8601 checks |
| **httpx** | HTTP client | Gateway → Account Service (sync REST with timeout/retry) |
| **stdlib `logging` + JSON formatter** | Observability | Structured logs (trace ID, timestamp, level, service name) |
| **SQLAlchemy + SQLite** | Database | `gateway.db` and `account.db` (separate per service); tables created on startup |
| **Pydantic Settings** | Configuration | `.env` / environment variables via `gateway/config.py`, `account/config.py` |
| **pytest + FastAPI TestClient** | Testing | Unit and integration tests |
| **Docker + Docker Compose** | Deployment | Two containers, healthcheck, service discovery |

No external databases, message brokers, or observability platforms were added beyond the assignment scope.

---

## What was asked vs what was done

### Architecture

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Two independent microservices | Done | `services/event_gateway`, `services/account_service` |
| Python + FastAPI | Done | Both services use FastAPI + Uvicorn |
| Browser → Event Gateway only (public) | Done | Gateway on port 8000 |
| Gateway → Account Service sync REST | Done | `gateway/account_client.py` (`httpx`) |
| Account Service internal | Done | Port 8001; compose wires `ACCOUNT_SERVICE_URL` |
| Separate embedded SQLite DB per service | Done | `gateway.db` / `account.db` via `gateway/models.py`, `account/models.py` |
| No shared DB or in-process state | Done | Separate processes and stores |
| Clear API contracts | Done | See README + OpenAPI at `/docs` |

### Event Gateway endpoints

| Endpoint | Status | Location |
|----------|--------|----------|
| `POST /events` | Done | `gateway/routes.py` |
| `GET /events/{id}` | Done | `gateway/routes.py` |
| `GET /events?account={accountId}` | Done | `gateway/routes.py` (sorted by `eventTimestamp`) |
| `GET /health` | Done | `gateway/routes.py` |

### Account Service endpoints

| Endpoint | Status | Location |
|----------|--------|----------|
| `POST /accounts/{accountId}/transactions` | Done | `account/routes.py` |
| `GET /accounts/{accountId}/balance` | Done | `account/routes.py` |
| `GET /accounts/{accountId}` | Done | `account/routes.py` |
| `GET /health` | Done | `account/routes.py` |

### Event payload and validation

| Rule | Status | How |
|------|--------|-----|
| `eventId` required | Done | Pydantic `Field(..., min_length=1)` |
| `accountId` required | Done | Same |
| `type` required, CREDIT or DEBIT | Done | `Literal["CREDIT", "DEBIT"]` |
| `amount` required, > 0 | Done | `Field(..., gt=0)` |
| `currency` required | Done | `Field(..., min_length=1)` |
| `eventTimestamp` required, ISO 8601 | Done | Custom validator in `schemas.py` |
| `metadata` optional | Done | `Optional` field |
| Meaningful errors, correct HTTP codes | Done | `422` for validation; custom handler messages |

### Core functionality

| Behavior | Status | How |
|----------|--------|-----|
| Gateway validates input | Done | `EventRequest` model |
| Gateway enforces idempotency | Done | Lookup by `eventId` in SQLite before processing; duplicate → `200` + stored body |
| First `POST /events` returns `201` | Done | `response.status_code = 201` after successful create |
| Duplicate `POST /events` returns `200` | Done | Early return when `eventId` already exists |
| Gateway stores events | Done | After successful Account Service call |
| Gateway calls Account Service to apply tx | Done | `account_client.apply_transaction()` |
| Duplicate `eventId` does not double balance | Done | Gateway skip + Account idempotent on `eventId` |
| Duplicate returns original event | Done | `200` with same JSON |
| Out-of-order events OK | Done | Balance = Σ CREDIT − Σ DEBIT (order-independent) |
| List events by `eventTimestamp` | Done | `list_by_account()` sorts ascending |
| Net balance correct | Done | `compute_balance()` in Account Service |

**Processing order (important):** On `POST /events`, the Gateway checks idempotency first, calls Account Service, then persists the event only if the downstream call succeeds. This avoids storing events that were never applied when Account Service is down.

### Distributed tracing

| Requirement | Status | How |
|-------------|--------|-----|
| Trace ID at Gateway | Done | Middleware generates or accepts `X-Trace-ID` |
| Propagate to Account Service | Done | Header on every `httpx` call |
| Structured logs with trace ID | Done | `logging_config.py` JSON formatter + `trace_id_var` |

### Observability

| Requirement | Status | How |
|-------------|--------|-----|
| JSON structured logs | Done | `JsonFormatter` — `timestamp`, `level`, `service`, `traceId`, `message` |
| `GET /health` both services | Done | Status + `databaseConnected` + metrics snapshot |
| Custom metric | Done | Request/error counts per endpoint (`metrics.py`); exposed on `/health` and `/metrics` |

### Resiliency

| Requirement | Status | How |
|-------------|--------|-----|
| Timeout + retry with backoff | Done | `account_client.py`: 2s timeout, 3 attempts, exponential backoff |
| No infinite retry | Done | `MAX_RETRIES = 3` |
| Account down → `POST /events` → 503 | Done | `AccountServiceError` → `HTTPException(503)` |
| GET events still work when Account down | Done | Reads Gateway DB only |
| Balance query clear error when unreachable | Done | `AccountServiceClient.get_balance()` raises `AccountServiceError(503)` |

### Docker

| Requirement | Status | How |
|-------------|--------|-----|
| `docker-compose.yml` | Done | Root `docker-compose.yml` |
| Dockerfiles | Done | Per-service `Dockerfile` |

### Automated tests (pytest)

| Area | Test file | Status |
|------|-----------|--------|
| Idempotency | `test_idempotency.py` | Done |
| Out-of-order handling | `test_out_of_order.py` | Done |
| Balance computation | `test_balance.py` | Done |
| Validation | `test_validation.py` | Done |
| Resiliency (Account failure) | `test_resiliency.py` | Done |
| Trace propagation | `test_trace.py` | Done |
| Integration (Gateway → Account) | `test_integration.py` | Done |

---

## How to run

### Option A — Docker Compose (recommended)

```bash
docker compose up --build
```

### Option B — Local with `.venv`

```powershell
cd c:\Users\dell\Documents\Downloads\event-ledger
.\.venv\Scripts\Activate.ps1

# Terminal 1
cd services\account_service
uvicorn account.main:app --port 8001 --reload

# Terminal 2
cd services\event_gateway
$env:ACCOUNT_SERVICE_URL = "http://localhost:8001"
uvicorn gateway.main:app --port 8000 --reload
```

### Run automated tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest -v
```

Expected: **13 tests passed**.

---

## How to verify each goal (manual + automated)

Use this checklist during a walkthrough or demo.

### 1. Services start and are healthy

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

**Pass if:** JSON includes `"status": "ok"`, `"databaseConnected": true`, and `metrics` object.

**Also verified by:** `test_integration.py` (health assertions).

---

### 2. Validation rejects bad events

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"eventId":"x","accountId":"a","type":"INVALID","amount":-1,"currency":"USD","eventTimestamp":"bad"}'
```

**Pass if:** HTTP `422` and `detail` mentions type/amount/timestamp issues.

**Also verified by:** `test_validation.py` (5 tests).

---

### 3. Happy path — event stored and balance updated

```bash
curl -X POST http://localhost:8000/events -H "Content-Type: application/json" -d '{
  "eventId": "evt-001",
  "accountId": "acct-123",
  "type": "CREDIT",
  "amount": 150.00,
  "currency": "USD",
  "eventTimestamp": "2026-05-15T14:02:11Z",
  "metadata": {"source": "mainframe-batch", "batchId": "B-9042"}
}'

curl http://localhost:8000/events/evt-001
curl "http://localhost:8000/events?account=acct-123"
curl http://localhost:8001/accounts/acct-123/balance
```

**Pass if:**

- First POST returns `201`
- GET by id returns same event
- List returns one event
- Balance is `150.0`

**Also verified by:** `test_integration.py`.

---

### 4. Idempotency

Submit the same `eventId` twice:

```bash
# Run the POST from step 3 again with the same eventId
```

**Pass if:**

- Second response is HTTP `200` (not `201`)
- Body matches first response
- Balance remains `150.0` (not `300.0`)

**Also verified by:** `test_idempotency.py`.

---

### 5. Out-of-order events and correct balance

Submit three events in non-chronological arrival order (see `test_out_of_order.py` for exact payloads):

- DEBIT 40 (latest timestamp) first  
- CREDIT 100 (earliest) second  
- CREDIT 25 (middle) third  

**Pass if:**

- Balance = 100 + 25 − 40 = **85.0**
- `GET /events?account=...` returns events sorted by `eventTimestamp` ascending

**Also verified by:** `test_out_of_order.py`.

---

### 6. Resiliency — Account Service unavailable

Stop Account Service (or point Gateway at a dead URL), then:

```bash
curl -X POST http://localhost:8000/events -H "Content-Type: application/json" -d '{...valid event...}'
```

**Pass if:** HTTP `503` with unavailable message; request does not hang.

With Gateway still up, previously stored events should still be readable:

```bash
curl http://localhost:8000/events/evt-001
```

**Pass if:** `200` for stored events (or `404` if none were stored before failure).

**Also verified by:** `test_resiliency.py`.

---

### 7. Trace propagation

```bash
curl -X POST http://localhost:8000/events \
  -H "X-Trace-ID: my-trace-123" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**Pass if:**

- Response header `X-Trace-ID: my-trace-123`
- Service logs (stdout) contain JSON with `"traceId": "my-trace-123"`

**Also verified by:** `test_trace.py` (header forwarded to Account Service).

---

### 8. Metrics

```bash
curl http://localhost:8000/metrics
curl http://localhost:8001/metrics
```

**Pass if:** JSON shows `requestCountByEndpoint` (and `errorCountByEndpoint` after errors).

---

### 9. Full automated confirmation

```bash
pytest -v
```

**Pass if:** All 13 tests pass — this is the fastest way to confirm the implementation meets the assignment goals.

| Test | Proves |
|------|--------|
| `test_validation.py` | Input rules and HTTP 422 |
| `test_idempotency.py` | No duplicate events or balance |
| `test_out_of_order.py` | Balance + sorted listing |
| `test_balance.py` | CREDIT − DEBIT math |
| `test_resiliency.py` | 503, balance client error, retry |
| `test_trace.py` | `X-Trace-ID` propagation |
| `test_integration.py` | End-to-end Gateway → Account |

---

## Design notes (for walkthrough)

### Idempotency (two layers)

1. **Gateway:** If `eventId` exists in local store → return `200` immediately (no downstream call).
2. **Account Service:** If `eventId` already applied for that account → return `200` without changing balance.

This protects against client retries and partial failures after Account Service succeeded but Gateway did not persist.

### Balance regardless of order

Transactions are stored in a map keyed by `eventId`. Balance is recomputed as:

```
balance = sum(CREDIT amounts) - sum(DEBIT amounts)
```

Arrival order does not affect the result.

### Resiliency pattern

**Chosen pattern:** Timeout + limited retries with exponential backoff.

| Setting | Default | Env var |
|---------|---------|---------|
| Timeout | 2s | `ACCOUNT_REQUEST_TIMEOUT` |
| Max retries | 3 | `ACCOUNT_MAX_RETRIES` |
| Backoff base | 0.1s | `ACCOUNT_BACKOFF_BASE` |

Retries apply to connection errors, timeouts, and HTTP 5xx. After exhaustion, Gateway returns **503** for `POST /events`.

### Configuration (`.env`)

Copy `.env.example` to `.env` at the project root. Services load it automatically (Pydantic Settings). See `.env.example` for all variables.

### SQLite persistence

| Service | File (local default) | Docker path | Env var |
|---------|----------------------|-------------|---------|
| Event Gateway | `gateway.db` | `/data/gateway.db` | `GATEWAY_DATABASE_URL` |
| Account Service | `account.db` | `/data/account.db` | `ACCOUNT_DATABASE_URL` |

Tables are created automatically on service startup (`init_db()` → SQLAlchemy `create_all`). Tests use isolated temp SQLite files per test function.

**Gateway tables:** `events`  
**Account tables:** `accounts`, `transactions`

Health checks run `SELECT 1` against the SQLite engine to set `databaseConnected`.

### What was intentionally not added

- External databases (PostgreSQL, etc.)
- Async messaging (Kafka, queues)
- Authentication / authorization
- Gateway proxy for balance (balance is queried on Account Service per spec)
- Extra endpoints beyond the problem statement

---

## File reference

| Path | Purpose |
|------|---------|
| `services/event_gateway/gateway/main.py` | Gateway app entry, middleware, validation handler |
| `services/event_gateway/gateway/routes.py` | Gateway HTTP handlers |
| `services/event_gateway/gateway/account_client.py` | Resilient HTTP client to Account Service |
| `services/event_gateway/gateway/models.py` | SQLAlchemy models (`events`) |
| `services/event_gateway/gateway/database.py` | SQLite repository / session management |
| `services/account_service/account/models.py` | SQLAlchemy models (`accounts`, `transactions`) |
| `services/account_service/account/routes.py` | Account HTTP handlers |
| `services/account_service/account/database.py` | SQLite repository / session management |
| `tests/` | pytest suite |
| `docker-compose.yml` | Orchestration |

---

## Summary

The project satisfies the take-home goals: two FastAPI microservices with separate SQLite databases, defined REST contracts, validation, idempotency (`201` create / `200` duplicate), correct balances for out-of-order events, distributed tracing, structured logging, health/metrics, resilient Gateway→Account calls, Docker packaging, and pytest coverage including integration tests.

**Quick confirmation:** `docker compose up --build` then `pytest -v` — all tests green and health endpoints return `ok`.
