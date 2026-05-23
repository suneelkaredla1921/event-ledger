# Event Ledger

A take-home implementation of a two-service event ledger: clients send financial transaction events to a public **Event Gateway**, which validates and stores them, then applies balances on an internal **Account Service** over synchronous REST.

## Tech stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12 |
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| Validation / schemas | Pydantic v2 |
| HTTP client (Gateway → Account) | httpx |
| Database | SQLAlchemy + SQLite (`gateway.db`, `account.db`) |
| Configuration | Pydantic Settings (`.env` via `pydantic-settings`) |
| Testing | pytest, pytest-asyncio, FastAPI TestClient |
| Containers | Docker, Docker Compose |

## Architecture

```
Browser / Client
       |
       v
+------------------+       synchronous REST        +-------------------+
|  Event Gateway   |  ------------------------->  |  Account Service  |
|  (public :8000)  |       X-Trace-ID header      |  (internal :8001) |
|  gateway.db      |                              |  account.db       |
+------------------+                              +-------------------+
```

- **Event Gateway** — Public API: event intake, validation, idempotency, local event storage in `gateway.db`.
- **Account Service** — Internal API: balances and transaction history in `account.db`. Databases are separate; no shared state.

### HTTP status codes (`POST /events`)

| Case | Status |
|------|--------|
| First successful submission | `201 Created` |
| Duplicate `eventId` (same body returned) | `200 OK` |

### Configuration (`.env`)

Settings are loaded from a `.env` file at the **project root** (and optional service-level `.env`). Copy the example file:

```powershell
copy .env.example .env
```

Sample `.env` (see `.env.example` for the full list):

```env
ACCOUNT_SERVICE_URL=http://localhost:8001
ACCOUNT_REQUEST_TIMEOUT=2
ACCOUNT_MAX_RETRIES=3
ACCOUNT_BACKOFF_BASE=0.1
GATEWAY_DATABASE_URL=sqlite:///./gateway.db
ACCOUNT_DATABASE_URL=sqlite:///./account.db
```

| Variable | Purpose |
|----------|---------|
| `ACCOUNT_SERVICE_URL` | Gateway → Account Service base URL |
| `ACCOUNT_REQUEST_TIMEOUT` | HTTP client timeout (seconds) |
| `ACCOUNT_MAX_RETRIES` | Max retry attempts |
| `ACCOUNT_BACKOFF_BASE` | Exponential backoff base (seconds) |
| `GATEWAY_DATABASE_URL` | Event Gateway SQLite URL |
| `ACCOUNT_DATABASE_URL` | Account Service SQLite URL |

`.env` is gitignored; `.env.example` is tracked as the template.

Docker Compose loads `.env` via `env_file` and overrides service-specific values (e.g. `ACCOUNT_SERVICE_URL=http://account-service:8001`) in `docker-compose.yml`.

## Prerequisites

- Python 3.12+
- Docker and Docker Compose (optional, for containerized run)

## Setup (virtual environment)

```powershell
cd c:\Users\dell\Documents\Downloads\event-ledger
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r services\account_service\requirements.txt -r services\event_gateway\requirements.txt -r requirements.txt
copy .env.example .env
```

## Run with Docker Compose

```bash
docker compose up --build
```

- Event Gateway: http://localhost:8000  
- Account Service: http://localhost:8001  

## Run locally (two terminals)

Ensure `.env` exists at the project root (`copy .env.example .env`). The Gateway reads `ACCOUNT_SERVICE_URL` automatically.

**Terminal 1 — Account Service**

```powershell
cd services\account_service
uvicorn account.main:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 — Event Gateway**

```powershell
cd services\event_gateway
uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

## Run tests

From the project root with `.venv` activated:

```bash
pytest
```

All tests should pass (see IMPLEMENTATION.md for what each test proves).

## Quick manual check

```powershell
# Submit an event
curl -X POST http://localhost:8000/events `
  -H "Content-Type: application/json" `
  -H "X-Trace-ID: demo-trace-1" `
  -d '{"eventId":"evt-001","accountId":"acct-123","type":"CREDIT","amount":150.00,"currency":"USD","eventTimestamp":"2026-05-15T14:02:11Z"}'

# Read balance (Account Service)
curl http://localhost:8001/accounts/acct-123/balance

# Health
curl http://localhost:8000/health
curl http://localhost:8001/health
```

Interactive API docs: http://localhost:8000/docs and http://localhost:8001/docs

## API summary

| Service | Endpoints |
|---------|-----------|
| Event Gateway | `POST /events`, `GET /events/{id}`, `GET /events?account={accountId}`, `GET /health`, `GET /metrics` |
| Account Service | `POST /accounts/{accountId}/transactions`, `GET /accounts/{accountId}/balance`, `GET /accounts/{accountId}`, `GET /health`, `GET /metrics` |

## Project layout

```
event-ledger/
├── README.md                 # This file — quick start
├── .env.example              # Configuration template (copy to .env)
├── docker-compose.yml
├── requirements.txt
├── services/
│   ├── account_service/      # Account Service (package: account)
│   └── event_gateway/        # Event Gateway (package: gateway)
└── tests/                    # pytest suite
```

