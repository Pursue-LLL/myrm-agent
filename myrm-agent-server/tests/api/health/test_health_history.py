"""Tests for GET /api/v1/health/history (trend data)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError as SQLAlchemyOperationalError

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@asynccontextmanager
async def _session_context_no_such_table() -> object:
    class _Session:
        async def execute(self, *_args, **_kwargs) -> object:
            orig = Exception("no such table: system_health_history")
            raise SQLAlchemyOperationalError("SELECT ...", {}, orig)

    yield _Session()


def test_health_history_default_returns_200_with_data_key(client: TestClient) -> None:
    response = client.get("/api/v1/health/history")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert isinstance(body["data"], list)


def test_health_history_invalid_hours(client: TestClient) -> None:
    response = client.get("/api/v1/health/history?hours=0")
    assert response.status_code == 400

    response = client.get("/api/v1/health/history?hours=999")
    assert response.status_code == 400


def test_health_history_empty_when_table_missing_message(client: TestClient) -> None:
    with patch("app.api.health.router.get_session", _session_context_no_such_table):
        response = client.get("/api/v1/health/history?hours=24")
    assert response.status_code == 200
    assert response.json() == {"data": []}


@pytest.mark.parametrize("hours", [1, 24, 168])
def test_health_history_accepts_hour_boundaries(client: TestClient, hours: int) -> None:
    response = client.get(f"/api/v1/health/history?hours={hours}")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert isinstance(body["data"], list)


@asynccontextmanager
async def _session_context_one_row() -> object:
    class _Result:
        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                (
                    "2026-01-15T12:00:00+00:00",
                    "pass",
                    88,
                    '{"harness":[],"server":[]}',
                )
            ]

    class _Session:
        async def execute(self, *_args, **_kwargs) -> _Result:
            return _Result()

    yield _Session()


def test_health_history_row_keys_match_contract(client: TestClient) -> None:
    with patch("app.api.health.router.get_session", _session_context_one_row):
        response = client.get("/api/v1/health/history?hours=1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    row = data[0]
    assert set(row) == {"timestamp", "status", "score", "components"}
    assert row["status"] == "pass"
    assert row["score"] == 88
    assert row["components"] == '{"harness":[],"server":[]}'
