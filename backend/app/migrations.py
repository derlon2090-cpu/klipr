"""Minimal idempotent SQL migration runner for PostgreSQL deployments."""
from pathlib import Path
from sqlalchemy import text

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def apply_migrations(engine) -> None:
    """Apply each numbered migration once after the declarative base exists."""
    if engine is None or engine.dialect.name != "postgresql":
        return
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))
        applied = {row[0] for row in connection.execute(text("SELECT name FROM schema_migrations"))}
        for file in files:
            if file.name in applied:
                continue
            # Migration files are repository-controlled SQL, never user input.
            connection.execute(text(file.read_text(encoding="utf-8")))
            connection.execute(text("INSERT INTO schema_migrations (name) VALUES (:name)"), {"name": file.name})
