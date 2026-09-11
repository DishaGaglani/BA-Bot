import os
import sys
import uuid
import time
import json
import logging
import requests
from dotenv import load_dotenv
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from database import SessionLocal

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] traceId=%(traceId)s %(message)s"
)
logger = logging.getLogger("ba-bot")

# --- Retries with Exponential Backoff ---
def request_with_retry(method: str, url: str, **kwargs):
    max_retries = 3
    backoff = 1.0  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            if "timeout" not in kwargs:
                kwargs["timeout"] = (5, 90)
            elif isinstance(kwargs["timeout"], (int, float)):
                kwargs["timeout"] = (5, kwargs["timeout"])
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as exc:
            if attempt == max_retries:
                logger.error(f"Request to {url} failed after {max_retries} attempts: {str(exc)}", extra={"traceId": "system"})
                raise exc
            sleep_time = backoff * (2 ** (attempt - 1))
            logger.warning(
                f"Request to {url} failed (attempt {attempt}/{max_retries}). Retrying in {sleep_time}s... Error: {str(exc)}",
                extra={"traceId": "system"}
            )
            time.sleep(sleep_time)

# --- Environment Validation ---
def validate_environment():
    logger.info("Validating environment variables...", extra={"traceId": "startup"})
    
    # 1. JWT Secret
    jwt_secret = os.getenv("JWT_SECRET")
    if os.getenv("ENV") == "production":
        if not jwt_secret:
            logger.critical("CRITICAL: JWT_SECRET environment variable is missing in production environment!", extra={"traceId": "startup"})
            sys.exit(1)
        if len(jwt_secret) < 32 or jwt_secret == "development_secret_key_change_me_in_production":
            logger.critical("CRITICAL: JWT_SECRET is insecure in production environment!", extra={"traceId": "startup"})
            sys.exit(1)
    else:
        if not jwt_secret:
            logger.warning("Warning: JWT_SECRET is not set. Using default developer configurations.", extra={"traceId": "startup"})
            
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
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.error(f"HTTPException: {exc.detail}", extra={"traceId": trace_id})
        return make_error_response(exc.detail, f"HTTP_{exc.status_code}", trace_id, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.error(f"Validation Error: {exc.errors()}", extra={"traceId": trace_id})
        return make_error_response("Invalid request payload parameters.", "VALIDATION_ERROR", trace_id, 422)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.exception(f"Unhandled Exception: {str(exc)}", extra={"traceId": trace_id})
        return make_error_response("An unexpected internal server error occurred.", "INTERNAL_SERVER_ERROR", trace_id, 500)
