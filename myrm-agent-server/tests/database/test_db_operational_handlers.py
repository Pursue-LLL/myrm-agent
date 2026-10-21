"""Tests for app.database.operations.db_operational_handlers."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import DBAPIError

from app.database.operations.db_operational_handlers import register_database_operational_handlers


@pytest.fixture()
def app_with_handlers() -> FastAPI:
    app = FastAPI()
    register_database_operational_handlers(app)

    @app.get("/sqlite-busy")
    async def _raise_busy() -> None:
        raise sqlite3.OperationalError("database is locked")

    @app.get("/sqlite-error")
    async def _raise_error() -> None:
        raise sqlite3.OperationalError("disk I/O error")

    @app.get("/sqlalchemy-busy")
    async def _raise_sa_busy() -> None:
        orig = sqlite3.OperationalError("database is locked")
        raise DBAPIError.instance(
            statement="SELECT 1",
            params=None,
            orig=orig,
            dbapi_base_err=sqlite3.Error,
        )

    @app.get("/sqlalchemy-error")
    async def _raise_sa_error() -> None:
        orig = sqlite3.OperationalError("no such table: foo")
        raise DBAPIError.instance(
            statement="SELECT 1",
            params=None,
            orig=orig,
            dbapi_base_err=sqlite3.Error,
        )

    return app


@pytest.fixture()
async def client(app_with_handlers: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app_with_handlers)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestSqlite3OperationalHandler:
    @pytest.mark.asyncio
    async def test_busy_returns_503(self, client: AsyncClient) -> None:
        with patch(
            "app.database.operations.sqlite_storage_busy.get_sqlite_busy_timeout_ms",
            return_value=5000,
        ):
            resp = await client.get("/sqlite-busy")
        assert resp.status_code == 503
        body = resp.json()
        assert body["code"] == 51005
        assert "Retry-After" in resp.headers
        assert resp.headers["Retry-After"] == "5"

    @pytest.mark.asyncio
    async def test_non_busy_returns_500(self, client: AsyncClient) -> None:
        resp = await client.get("/sqlite-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 51002


class TestSQLAlchemyOperationalHandler:
    @pytest.mark.asyncio
    async def test_busy_returns_503(self, client: AsyncClient) -> None:
        with patch(
            "app.database.operations.sqlite_storage_busy.get_sqlite_busy_timeout_ms",
            return_value=5000,
        ):
            resp = await client.get("/sqlalchemy-busy")
        assert resp.status_code == 503
        body = resp.json()
        assert body["code"] == 51005

    @pytest.mark.asyncio
    async def test_non_busy_returns_500(self, client: AsyncClient) -> None:
        resp = await client.get("/sqlalchemy-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 51002
