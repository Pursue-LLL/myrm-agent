"""Integration: chat processor file_id == Artifact.id == publish lookup."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.files.hosting_api import router as hosting_router
from app.core.artifacts.listener import ensure_artifact_for_deploy, upsert_processor_artifact
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.hosting.packager import PublishFile
from app.services.hosting.preflight import DeployPreflightResult
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID, save_hosting_targets
from app.services.hosting.types import HostingTarget


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_file_id_chain?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def publish_client(db_session: AsyncSession) -> TestClient:
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(hosting_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    limiter.enabled = True


@pytest.mark.asyncio
async def test_upsert_processor_artifact_keys_db_row_by_file_id(db_session: AsyncSession, tmp_path) -> None:
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
async def test_ensure_artifact_for_deploy_resolves_processor_file_id(db_session: AsyncSession, tmp_path) -> None:
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
async def test_publish_api_accepts_processor_file_id_not_uuid(
    publish_client: TestClient, db_session: AsyncSession, tmp_path
) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=LEGACY_VERCEL_TARGET_ID,
                name="Vercel",
                provider_type="vercel",
                config={},
                is_default=True,
            )
        ],
    )

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

    mock_version = MagicMock()
    mock_version.id = "version-001"
    mock_version.created_at = MagicMock()
    mock_artifact = MagicMock(spec=Artifact)
    mock_artifact.id = file_id
    mock_artifact.name = "index.html"
    mock_artifact.versions = [mock_version]

    publish_files = {"index.html": PublishFile(path="index.html", content="<h1>Hello</h1>")}

    with patch(
        "app.api.files.hosting_api.run_deploy_preflight",
        new_callable=AsyncMock,
        return_value=DeployPreflightResult(
            deployable=True,
            reason="OK",
            message="OK",
            hint=None,
        ),
    ):
        with patch(
            "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
            new_callable=AsyncMock,
            return_value=(mock_artifact, publish_files),
        ):
            with patch("app.services.hosting.providers.vercel.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.deploy = AsyncMock(
                    return_value={
                        "deployment_id": "dep_file_id",
                        "url": "https://file-id-chain.vercel.app",
                        "project_id": "prj_file_id",
                        "status": "READY",
                    }
                )

                response = publish_client.post(
                    f"/{file_id}/publish",
                    json={"target_id": LEGACY_VERCEL_TARGET_ID, "token": "test_token"},
                )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://file-id-chain.vercel.app"
    assert data["publication_version_id"] == "version-001"
