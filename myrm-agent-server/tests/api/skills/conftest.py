"""Skills API test fixtures."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def app() -> FastAPI:
    """Create minimal test app for skills API."""
    from importlib import import_module

    app = FastAPI(title="Skills Test App")

    # Include skills router
    skills_module = import_module("app.api.skills.router")
    app.include_router(skills_module.router, prefix="/api/v1/skills", tags=["skills"])
    growth_module = import_module("app.api.skills.growth")
    app.include_router(growth_module.router, prefix="/api/v1", tags=["skill-growth"])
    evolution_module = import_module("app.api.skills.evolution")
    app.include_router(evolution_module.router, prefix="/api/v1", tags=["evolution"])

    return app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)

@pytest.fixture(autouse=True)
async def setup_test_database():
    """Initialize an in-memory SQLite database with schema for tests."""
    from unittest.mock import patch

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.database.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_get_session():
        async with TestSession() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return TestSession

    with (
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.services.agent.backends.profile_backend.get_session", mock_get_session),
        patch("app.services.approvals.registry.get_session", mock_get_session),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
        patch("app.database.repositories.uow.get_session_factory", mock_get_session_factory),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
    ):
        yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
