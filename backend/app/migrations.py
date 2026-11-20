"""Minimal idempotent SQL migration runner for PostgreSQL deployments."""
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _apply_migrations(connection: Connection) -> None:
    """Apply pending migrations using the caller's transaction."""
    connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"))
    applied = {row[0] for row in connection.execute(text("SELECT name FROM schema_migrations"))}
    for file in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        if file.name in applied:
            continue
        # Migration files are repository-controlled SQL, never user input.
        # PostgreSQL drivers can reject a multi-statement prepared query.
        for statement in file.read_text(encoding="utf-8").split(";"):
            statement = "\n".join(
                line for line in statement.splitlines() if not line.lstrip().startswith("--")
            ).strip()
            if statement:
                connection.execute(text(statement))
        connection.execute(text("INSERT INTO schema_migrations (name) VALUES (:name)"), {"name": file.name})


def apply_migrations(bind: Engine | Connection | None) -> None:
    """Apply each numbered migration once after the declarative base exists.

    A Connection lets serverless startup keep schema creation and migrations in
    one advisory-locked transaction. Engine support is retained for scripts.
    """
    if bind is None or bind.dialect.name != "postgresql":
        return
    if isinstance(bind, Connection):
        _apply_migrations(bind)
        return
    with bind.begin() as connection:
        _apply_migrations(connection)
