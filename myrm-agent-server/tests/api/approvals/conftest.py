"""Approvals API test fixtures."""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.approvals.router import router as approvals_router
from app.database.models import Base


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Approvals Test App")
    test_app.include_router(approvals_router, prefix="/api/v1")
    return test_app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
async def setup_test_database():
    """In-memory SQLite with approval schema for registry tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def mock_get_session():
        async with test_session() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return test_session

    with (
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.services.approvals.registry.get_session", mock_get_session),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
        patch("app.database.repositories.uow.get_session_factory", mock_get_session_factory),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
    ):
        yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
