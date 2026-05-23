import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from account import metrics
from account.logging_config import setup_logging, trace_id_var
from account.routes import router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from account.database import init_db

    init_db()
    logger.info("Account SQLite database initialized")
    yield


app = FastAPI(title="Account Service", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def trace_and_metrics_middleware(request: Request, call_next):
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
        if loc:
            errors.append(f"{loc}: {msg}")
        else:
            errors.append(msg)
    return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})


@app.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()
