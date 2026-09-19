"""Engine, session factory and the FastAPI dependency.

Synchronous SQLAlchemy 2.0 on psycopg 3. The workload here is short
transactional reads and writes against indexed tables; async would add a colour
to every function in the codebase and buy nothing measurable at this size.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                            future=True)


def get_db() -> Iterator[Session]:
    """Request-scoped session. Commits are explicit in the service layer."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_healthy() -> tuple[bool, str]:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # pragma: no cover - reported through /health
        return False, str(exc)[:200]
