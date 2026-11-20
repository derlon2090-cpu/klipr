from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

def sqlalchemy_database_url(value: str | None) -> str | None:
    """Select the installed psycopg v3 driver for ordinary Postgres URLs."""
    if value and value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    if value and value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    return value


database_url = sqlalchemy_database_url(get_settings().database_url)
# Serverless health and authentication endpoints must be able to start even
# when the database environment variable has not been configured yet.
engine = create_engine(database_url, pool_pre_ping=True) if database_url else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
