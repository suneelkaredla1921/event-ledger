import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gateway import metrics
from gateway.logging_config import setup_logging, trace_id_var
from gateway.routes import router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from gateway.database import init_db

    init_db()
    logger.info("Gateway SQLite database initialized")
    yield


app = FastAPI(title="Event Gateway API", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    trace_id_var.set(trace_id)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    metrics.record_error(request.url.path)
    errors = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
        msg = err.get("msg", "Invalid value")
        field = loc.split(".")[-1] if loc else "request"
        if "required" in msg.lower() or err.get("type") == "missing":
            errors.append(f"{field} is required")
        elif field == "type" and "literal" in err.get("type", ""):
            errors.append("type must be CREDIT or DEBIT")
        elif field == "amount":
            errors.append("amount must be greater than 0")
        elif field == "eventTimestamp":
            errors.append("eventTimestamp must be a valid ISO 8601 datetime")
        else:
            errors.append(f"{field}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})


@app.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()
