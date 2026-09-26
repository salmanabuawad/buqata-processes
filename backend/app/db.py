from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import JSON, DateTime, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings
from app.core.clock import ensure_utc

JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """timestamptz on PostgreSQL; on SQLite the zone is restored on read."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return ensure_utc(value)

    def process_result_value(self, value, dialect):
        return ensure_utc(value)


class Base(DeclarativeBase):
    type_annotation_map = {}


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
