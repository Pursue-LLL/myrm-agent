"""Integration: chat processor file_id == Artifact.id == deploy lookup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.files.deploy_api import router as deploy_router
from app.core.artifacts.listener import ensure_artifact_for_deploy, upsert_processor_artifact
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.deploy.deploy_packager import DeployFile


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_file_id_chain?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def deploy_client(db_session: AsyncSession) -> TestClient:
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(deploy_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    limiter.enabled = True


@pytest.mark.asyncio
async def test_upsert_processor_artifact_keys_db_row_by_file_id(
    db_session: AsyncSession, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    html_file = workspace / "index.html"
    html_file.write_text("<h1>Deploy me</h1>", encoding="utf-8")

    file_id = "processor-file-id-001"

    version_id = await upsert_processor_artifact(
        db_session,
        file_id=file_id,
        filename="index.html",
        sandbox_path=str(html_file),
        workspace_root=str(workspace),
        chat_id="chat-integration-1",
    )

    artifact = await db_session.get(Artifact, file_id)
    assert artifact is not None
    assert artifact.id == file_id
    assert artifact.name == "index.html"
    assert artifact.chat_id == "chat-integration-1"

    version = await db_session.get(ArtifactVersion, version_id)
    assert version is not None
    assert version.artifact_id == file_id


@pytest.mark.asyncio
async def test_ensure_artifact_for_deploy_resolves_processor_file_id(
    db_session: AsyncSession, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    html_file = workspace / "landing.html"
    html_file.write_text("<html><body>Live</body></html>", encoding="utf-8")

    file_id = "processor-file-id-002"
    await upsert_processor_artifact(
        db_session,
        file_id=file_id,
        filename="landing.html",
        sandbox_path=str(html_file),
        workspace_root=str(workspace),
    )

    loaded = await ensure_artifact_for_deploy(db_session, file_id, str(workspace))

    assert loaded.id == file_id
    assert loaded.versions
    assert loaded.versions[-1].artifact_id == file_id


@pytest.mark.asyncio
async def test_deploy_api_accepts_processor_file_id_not_uuid(
    deploy_client: TestClient, db_session: AsyncSession, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    html_file = workspace / "index.html"
    html_file.write_text("<h1>Hello</h1>", encoding="utf-8")

    file_id = "sse-artifact-file-id-003"
    await upsert_processor_artifact(
        db_session,
        file_id=file_id,
        filename="index.html",
        sandbox_path=str(html_file),
        workspace_root=str(workspace),
    )

    with patch("app.api.files.deploy_api.get_workspace_root", return_value=tmp_path):
        with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
            mock_vault_class.return_value.get_object_path.return_value = MagicMock()

            with patch("app.api.files.deploy_api.collect_deploy_files") as mock_collect:
                mock_collect.return_value = {
                    "index.html": DeployFile(path="index.html", content="<h1>Hello</h1>"),
                }

                with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                    mock_vercel_instance = mock_vercel_class.return_value
                    mock_vercel_instance.deploy = AsyncMock(
                        return_value={
                            "deployment_id": "dep_file_id",
                            "url": "https://file-id-chain.vercel.app",
                            "project_id": "prj_file_id",
                            "status": "READY",
                        }
                    )

                    response = deploy_client.post(
                        f"/{file_id}/deploy",
                        json={"token": "test_token", "platform": "vercel"},
                    )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://file-id-chain.vercel.app"
    assert data["deployment_version_id"] is not None

    artifact = await db_session.get(Artifact, file_id)
    assert artifact is not None
    assert artifact.deployment_url == "https://file-id-chain.vercel.app"
    assert artifact.deployment_status == "READY"
    assert artifact.deployment_version_id is not None
