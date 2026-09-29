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
    # timeout=15 is sqlite3's busy_timeout: how long a connection waits for another
    # writer to release its lock before raising "database is locked", instead of
    # sqlite3's own default of 5s. Startup runs several back-to-back write
    # transactions (schema adoption, dedup, seeding); a low timeout could raise
    # OperationalError before reaching the integrity-error rollback handling.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15}
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