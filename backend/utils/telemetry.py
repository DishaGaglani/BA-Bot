import os
import sys
import time
from time import perf_counter
import json
import logging
import requests
from dotenv import load_dotenv
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from traceid import TraceId
from database import SessionLocal

# Load environment variables
load_dotenv()

# Configure logging
class _DefaultTraceIdFilter(logging.Filter):
    """The format string below requires a traceId on every record, but only our
    own calls pass extra={"traceId": ...}. Records from anywhere else (third-party
    libraries, or a call that forgot it) would otherwise raise KeyError inside the
    handler and lose the log line. This fills in "-" only when the field is
    missing, so records that do carry a traceId are left untouched. It's attached
    to the handler, not set via a LogRecord factory: extra= is applied after the
    factory runs and refuses to overwrite an existing attribute."""
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "traceId"):
            record.traceId = "-"
        return True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] traceId=%(traceId)s %(message)s"
)
for _handler in logging.getLogger().handlers:
    if not any(isinstance(f, _DefaultTraceIdFilter) for f in _handler.filters):
        _handler.addFilter(_DefaultTraceIdFilter())
logger = logging.getLogger("ba-bot")

def new_trace_id() -> str:
    """Generate a fresh trace id via the traceid library instead of calling
    uuid.uuid4() directly, so ID generation lives in one place backed by a
    maintained library rather than an inline stdlib call. traceid stores the
    value in a contextvar, which we don't otherwise rely on here (the trace id
    is still threaded explicitly via request.state / extra={"traceId": ...}) so
    each call clears any prior value first rather than reusing the ambient one."""
    TraceId.clear()
    TraceId.gen()
    return str(TraceId.get())

# --- Retries with Exponential Backoff ---
def request_with_retry(method: str, url: str, **kwargs):
    max_retries = 3
    backoff = 1.0  # seconds
    started = perf_counter()
    for attempt in range(1, max_retries + 1):
        try:
            if "timeout" not in kwargs:
                kwargs["timeout"] = (5, 90)
            elif isinstance(kwargs["timeout"], (int, float)):
                kwargs["timeout"] = (5, kwargs["timeout"])
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            response_time = (perf_counter() - started) * 1000
            logger.info(
                f"LLM call to {url} succeeded on attempt {attempt}/{max_retries} response_time={response_time:.2f}ms",
                extra={"traceId": "system"}
            )
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as exc:
            if attempt == max_retries:
                response_time = (perf_counter() - started) * 1000
                logger.error(
                    f"Request to {url} failed after {max_retries} attempts response_time={response_time:.2f}ms: {str(exc)}",
                    extra={"traceId": "system"}
                )
                raise exc
            sleep_time = backoff * (2 ** (attempt - 1))
            logger.warning(
                f"Request to {url} failed (attempt {attempt}/{max_retries}). Retrying in {sleep_time}s... Error: {str(exc)}",
                extra={"traceId": "system"}
            )
            time.sleep(sleep_time)


# --- Database query latency ---
def instrument_db_latency(engine) -> None:
    """Logs each SQL statement's wall-clock duration. Call once at startup, right after
    the engine is created (app.py does this alongside validate_environment()). Attaching
    the listeners more than once per engine would double-log every query, so this is not
    meant to be called per-request."""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._telemetry_query_start = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started = getattr(context, "_telemetry_query_start", None)
        if started is None:
            return
        response_time = (perf_counter() - started) * 1000
        # First line only: statements can be long (bulk inserts), and the operation
        # (SELECT/INSERT/...) is what matters for a latency log line, not the full SQL.
        first_line = statement.strip().splitlines()[0][:80]
        logger.debug(f"DB query response_time={response_time:.2f}ms: {first_line}")

# --- Environment Validation ---
def validate_environment():
    logger.info("Validating environment variables...", extra={"traceId": "startup"})
    
    # 1. JWT Secret
    jwt_secret = os.getenv("JWT_SECRET")
    is_weak_secret = bool(jwt_secret) and (len(jwt_secret) < 32 or jwt_secret == "development_secret_key_change_me_in_production")
    if os.getenv("ENV") == "production":
        if not jwt_secret:
            logger.critical("CRITICAL: JWT_SECRET environment variable is missing in production environment!", extra={"traceId": "startup"})
            sys.exit(1)
        if is_weak_secret:
            logger.critical("CRITICAL: JWT_SECRET is insecure in production environment!", extra={"traceId": "startup"})
            sys.exit(1)
    else:
        if not jwt_secret:
            logger.warning("Warning: JWT_SECRET is not set. Using a random per-process secret (tokens won't survive a restart).", extra={"traceId": "startup"})
        elif is_weak_secret:
            logger.warning("Warning: JWT_SECRET is set but is short or a known placeholder value. This is unsafe if this environment is network-reachable.", extra={"traceId": "startup"})

    # 2. Database validation
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Database connection validated successfully.", extra={"traceId": "startup"})
    except Exception as e:
        logger.critical(f"CRITICAL: Database connection failed during startup: {str(e)}", extra={"traceId": "startup"})
        sys.exit(1)
        
    # 3. Model Configuration & Endpoint
    prediction_url = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")
    if not prediction_url:
        logger.critical("CRITICAL: PREDICTION_URL is not configured!", extra={"traceId": "startup"})
        sys.exit(1)
        
    # 4. Upload directory validation
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    try:
        os.makedirs(upload_dir, exist_ok=True)
        test_file = os.path.join(upload_dir, ".startup_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        logger.info(f"Upload directory '{upload_dir}' verified successfully.", extra={"traceId": "startup"})
    except Exception as e:
        logger.critical(f"CRITICAL: Upload directory '{upload_dir}' is not writable: {str(e)}", extra={"traceId": "startup"})
        sys.exit(1)

# --- Standardized Error Response Formatter ---
def make_error_response(message: str, error_code: str, trace_id: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
            "errorCode": error_code,
            "traceId": trace_id
        }
    )

def setup_global_exception_handlers(app):
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        trace_id = getattr(request.state, "trace_id", None) or new_trace_id()
        logger.error(f"HTTPException: {exc.detail}", extra={"traceId": trace_id})
        return make_error_response(exc.detail, f"HTTP_{exc.status_code}", trace_id, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", None) or new_trace_id()
        logger.error(f"Validation Error: {exc.errors()}", extra={"traceId": trace_id})
        return make_error_response("Invalid request payload parameters.", "VALIDATION_ERROR", trace_id, 422)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", None) or new_trace_id()
        logger.exception(f"Unhandled Exception: {str(exc)}", extra={"traceId": trace_id})
        return make_error_response("An unexpected internal server error occurred.", "INTERNAL_SERVER_ERROR", trace_id, 500)
