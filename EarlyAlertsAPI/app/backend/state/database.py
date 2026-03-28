"""SQLite engine + connection factory using SQLAlchemy Core."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import Connection, create_engine, Engine

from app.backend.state.tables import metadata

_engine: Engine | None = None


def init_db(sqlite_path: str) -> Engine:
    """Create tables (if not exist) and return the engine.

    Call once at application startup or before the first use.
    """
    global _engine
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{sqlite_path}"
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialised – call init_db() first.")
    return _engine


@contextmanager
def get_session() -> Generator[Connection, None, None]:
    """Yield a SQLAlchemy Core connection inside a transaction."""
    with get_engine().begin() as conn:
        yield conn
