"""Fixtures for files API tests."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.files.artifact_api import router as artifact_router
from app.database.connection import get_db
from app.database.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_artifact_api?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def client(db_session: AsyncSession) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(artifact_router, prefix="/api/v1/files/artifacts")

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
