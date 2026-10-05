"""Shared fixtures: isolated file-backed sqlite + FastAPI TestClient.

The app's real engine (postgresql) is never touched: get_db is overridden and
the TestClient is used WITHOUT entering its context manager, so the lifespan
(which would create_all on the postgres engine) never runs.
"""
import os
import tempfile
from pathlib import Path

import pytest

# Must be set BEFORE importing app.*: app.database builds the (postgres) engine
# at import time, which eagerly imports psycopg2. Tests never use that engine
# (get_db is overridden; lifespan is not entered), so sqlite URL is enough.
os.environ.setdefault("DATABASE_URL", "sqlite:///unused-default.db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan  # noqa: F401  (register mappers)


@pytest.fixture()
def db_factory(tmp_path):
    db_file = Path(tempfile.mkdtemp(dir=tmp_path)) / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    engine.dispose()


@pytest.fixture()
def session(db_factory):
    """A write/seed session; tests open OTHER sessions to assert against the DB."""
    db = db_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_factory):
    def _override_get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # NOTE: deliberately not `with TestClient(...)` -> lifespan stays off,
    # so no postgres connection is attempted.
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()
