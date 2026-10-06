import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'ba_bot.db')}")

if DATABASE_URL.startswith("sqlite"):
    # check_same_thread=False is required because SessionLocal is used across
    # FastAPI's request threads, but the flag is SQLite-specific — other drivers
    # (e.g. psycopg2) raise a TypeError if it's passed to them.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # pool_pre_ping guards against handing out a connection the DB/proxy already
    # closed (common after container restarts or network blips); pool_recycle
    # proactively drops connections before a server-side idle timeout kills them.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


def utcnow() -> datetime.datetime:
    """Drop-in replacement for the deprecated datetime.datetime.utcnow().

    Returns the current UTC time as a *naive* datetime, on purpose: every
    DateTime column stores naive UTC (SQLite has no timezone support), and the
    API serializes these values with .isoformat() for the frontend. Returning
    an aware datetime here would change what is stored and add a "+00:00"
    suffix to every timestamp in API responses. This is the replacement the
    Python docs recommend for utcnow(), without the deprecation warning.
    """
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
