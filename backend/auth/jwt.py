import datetime
import bcrypt
import jwt
import secrets

import os

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Generated fresh per process, never a fixed/known value, so a deployment that
# forgets to set JWT_SECRET fails to forgeable-but-guessable rather than
# fails to a string visible to anyone who has read this file. Tokens signed
# with this fallback simply stop validating on the next restart.
_FALLBACK_SECRET = secrets.token_hex(32)


def _get_secret_key() -> str:
    """Read JWT_SECRET from the environment on every call (never cached at
    import time), so setting/rotating it takes effect immediately regardless
    of when this module was first imported relative to config loading."""
    return os.getenv("JWT_SECRET") or _FALLBACK_SECRET

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: datetime.timedelta | None = None) -> str:
    """Generate a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
