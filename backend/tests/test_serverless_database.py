from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app.main as main


class FakeEngine:
    def __init__(self):
        self.connection = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    @contextmanager
    def begin(self):
        yield self.connection


def test_schema_initialization_runs_once_per_cold_start(monkeypatch):
    fake_engine = FakeEngine()
    create_all = Mock()
    migrations = Mock()
    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(main, "apply_migrations", migrations)
    monkeypatch.setattr(main, "_schema_initialized", False)

    main.ensure_database_schema()
    main.ensure_database_schema()

    create_all.assert_called_once_with(bind=fake_engine.connection)
    migrations.assert_called_once_with(fake_engine.connection)


def test_schema_initialization_explains_missing_database(monkeypatch):
    monkeypatch.setattr(main, "engine", None)
    monkeypatch.setattr(main, "_schema_initialized", False)

    with pytest.raises(main.DatabaseUnavailable, match="DATABASE_URL"):
        main.ensure_database_schema()
