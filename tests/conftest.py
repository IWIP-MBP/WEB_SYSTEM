"""Shared pytest fixtures and test environment setup.

Environment variables required by ``database.py`` (which validates them at
import time) are configured here *before* any application module is imported.
A dummy PostgreSQL URL is used so that ``create_engine`` succeeds without
opening a real connection, while the actual DB-backed tests run against an
isolated in-memory SQLite database created from the shared ``metadata``.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import metadata


@pytest.fixture
def db():
    """Yield an isolated SQLite session with all tables created."""
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        metadata.drop_all(engine)
        engine.dispose()
