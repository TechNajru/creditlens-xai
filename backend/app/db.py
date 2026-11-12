"""Database engine/session. SQLite for local use; the schema is PostgreSQL-compatible
(generic types only; set CREDITLENS_DATABASE_URL to a postgresql+psycopg URL to switch).

All timestamps are stored as naive UTC datetimes (see utcnow()).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_factory: sessionmaker | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        url = config.database_url()
        if url.startswith("sqlite"):
            if ":memory:" not in url:
                path = url.split("///", 1)[-1]
                from pathlib import Path
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # SQLite ignores foreign keys unless asked
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        else:
            _engine = create_engine(url, pool_pre_ping=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Forget the cached engine (used by tests and when the database URL changes)."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


def get_session_factory() -> sessionmaker:
    get_engine()
    if _factory is None:
        raise RuntimeError("database engine was not initialised")
    return _factory


def get_db():
    db: Session = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
