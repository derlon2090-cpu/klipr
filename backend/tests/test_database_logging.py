from app.main import _database_error_summary


def test_database_error_summary_redacts_postgres_credentials():
    error = RuntimeError(
        "connection failed for postgresql+psycopg://user:secret@db.example/app"
    )
    summary = _database_error_summary(error)
    assert "user" not in summary
    assert "secret" not in summary
    assert "postgresql+psycopg://***@db.example/app" in summary
