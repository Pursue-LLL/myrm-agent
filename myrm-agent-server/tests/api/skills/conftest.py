"""Skills API test fixtures."""

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_DRAFTS_MODULE = None


def _load_drafts_module():
    """Load drafts router without importing app.api.skills package __init__."""
    global _DRAFTS_MODULE
    if _DRAFTS_MODULE is not None:
        return _DRAFTS_MODULE

    drafts_path = (
        Path(__file__).resolve().parents[3] / "app" / "api" / "skills" / "drafts.py"
    )
    spec = importlib.util.spec_from_file_location("app.api.skills.drafts", drafts_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load drafts module from {drafts_path}")
    import sys

    module = importlib.util.module_from_spec(spec)
    sys.modules["app.api.skills.drafts"] = module
    spec.loader.exec_module(module)
    _DRAFTS_MODULE = module
    return module


@pytest.fixture(scope="function")
def app() -> FastAPI:
    """Create minimal test app for skills API (drafts-only to avoid heavy harness imports)."""
    app = FastAPI(title="Skills Test App")
    drafts_module = _load_drafts_module()
    app.include_router(drafts_module.router, prefix="/api/v1/skills", tags=["skills-drafts"])
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

    _load_drafts_module()

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
        patch("app.api.skills.drafts.get_session", mock_get_session),
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
