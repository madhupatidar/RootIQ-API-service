"""PostgreSQL access: shared SQLAlchemy engine, session factory and schema bootstrap."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, SQL_DIR

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def run_schema() -> None:
    """Apply sql/schema.sql (idempotent CREATE TABLE IF NOT EXISTS statements)."""
    schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.exec_driver_sql(schema_sql)
