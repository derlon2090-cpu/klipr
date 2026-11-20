from app.db import sqlalchemy_database_url


def test_postgres_url_uses_installed_psycopg_v3_driver():
    value = "postgresql://user:secret@example.com/app?sslmode=require"
    assert sqlalchemy_database_url(value) == (
        "postgresql+psycopg://user:secret@example.com/app?sslmode=require"
    )


def test_database_url_preserves_explicit_dialects_and_missing_values():
    value = "postgresql+psycopg://user:secret@example.com/app"
    assert sqlalchemy_database_url(value) == value
    assert sqlalchemy_database_url(None) is None
