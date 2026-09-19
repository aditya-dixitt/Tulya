"""Test fixtures.

These run against a real PostgreSQL database, not SQLite. The schema uses JSONB
and Postgres CHECK constraints that carry governance rules; testing against a
different engine would test a different system.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _login(client: TestClient, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def as_viewer(client):
    return _login(client, "viewer", "viewer123")


@pytest.fixture
def as_steward(client):
    return _login(client, "steward", "steward123")


@pytest.fixture
def as_admin(client):
    return _login(client, "admin", "admin123")


@pytest.fixture(autouse=True)
def _clean_cookies(client):
    yield
    client.cookies.clear()
