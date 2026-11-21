"""Fixtures for files API tests."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_api import router as artifact_router
from app.api.files.artifact_share_api import public_router
from app.api.files.artifact_share_api import router as share_router
from app.api.files.hosting_api import router as hosting_router
from app.api.files.provenance_api import router as provenance_router
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion
from tests.support.chat_workspace import chats_bound_to_workspaces
from tests.support.hosting_api import CHAT_ID


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_artifact_api?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def html_artifact(db_session: AsyncSession) -> Artifact:
    """An html artifact with one version, the subject of the share tests."""
    artifact = Artifact(id=str(uuid.uuid4()), name="index.html", chat_id=str(uuid.uuid4()), is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()
    db_session.add(ArtifactVersion(id=str(uuid.uuid4()), artifact_id=artifact.id, vault_uri="vault://html", sha256_hash="hash"))
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Directory the share tests write vault objects into; a sibling of the state dir, which no workspace may contain."""
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def chats_share_workspace(workspace: Path) -> Iterator[None]:
    """Every chat the share tests mint ran in ``workspace``, where the tests write the vault objects."""
    with chats_bound_to_workspaces(default=workspace):
        yield


@pytest.fixture
def share_client(
    db_session: AsyncSession, tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """The artifact share management routes plus the public share routes (mounted under ``/public/artifact-share``)."""
    monkeypatch.setattr(
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
        str(tmp_path / "state"),
    )
    test_app = FastAPI()
    test_app.include_router(share_router)
    test_app.include_router(public_router, prefix="/public/artifact-share")

    async def override_get_db():
        yield db_session

    async def override_workspace_root() -> str:
        return str(workspace)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_workspace_root] = override_workspace_root
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def client(db_session: AsyncSession) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(provenance_router, prefix="/api/v1/files/artifacts")
    test_app.include_router(artifact_router, prefix="/api/v1/files/artifacts")

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def hosting_integration_client(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Path, AsyncSession]]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    test_app = FastAPI()
    test_app.include_router(hosting_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.api.files.hosting_api.get_workspace_root",
        lambda: workspace,
    )

    with chats_bound_to_workspaces({CHAT_ID: workspace}), TestClient(test_app) as test_client:
        yield test_client, workspace, db_session
