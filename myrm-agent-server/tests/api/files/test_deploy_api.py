import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.files.deploy_api import router as deploy_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.deploy.deploy_packager import DeployFile
from app.services.deploy.preflight import DeployPreflightResult


def _patch_deployable_preflight():
    return patch(
        "app.api.files.deploy_api.run_deploy_preflight",
        new_callable=AsyncMock,
        return_value=DeployPreflightResult(
            deployable=True,
            reason="OK",
            message="OK",
            hint=None,
        ),
    )


def _patch_resolve_deploy_files(artifact: Artifact, files: dict[str, DeployFile]):
    return patch(
        "app.api.files.deploy_api.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    )


@pytest.fixture
def deploy_client(db_session) -> TestClient:
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(deploy_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    limiter.enabled = True


@pytest.fixture
async def mock_artifact(db_session):
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="test-artifact",
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://test_uri",
        sha256_hash="test_hash",
    )
    db_session.add(version)
    await db_session.commit()
    loaded = await db_session.execute(
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact.id)
    )
    return loaded.scalar_one()


@pytest.fixture
async def artifact_without_versions(db_session):
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="empty-artifact",
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


@pytest.mark.asyncio
async def test_deploy_artifact_success(deploy_client, mock_artifact, db_session):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.deploy = AsyncMock(
                    return_value={
                        "deployment_id": "dep_123",
                        "url": "https://test.vercel.app",
                        "project_id": "prj_456",
                        "status": "READY",
                    }
                )

                response = deploy_client.post(
                    f"/{mock_artifact.id}/deploy",
                    json={"token": "test_token", "platform": "vercel"},
                )

                assert response.status_code == 200
                data = response.json()
                assert data["deployment_id"] == "dep_123"
                assert data["url"] == "https://test.vercel.app"
                assert data["deployment_version_id"] is not None
                assert data["latest_version_id"] is not None

                await db_session.refresh(mock_artifact)
                assert mock_artifact.deployment_url == "https://test.vercel.app"
                assert mock_artifact.deployment_status == "READY"
                assert mock_artifact.deployment_version_id is not None


@pytest.mark.asyncio
async def test_deploy_artifact_not_found(deploy_client):
    response = deploy_client.post(
        f"/{uuid.uuid4()}/deploy",
        json={"token": "test_token", "platform": "vercel"},
    )
    assert response.status_code == 400
    assert "Artifact not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_deploy_unsupported_platform(deploy_client, mock_artifact):
    response = deploy_client.post(
        f"/{mock_artifact.id}/deploy",
        json={"token": "test_token", "platform": "netlify"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Only Vercel is supported currently"


@pytest.mark.asyncio
async def test_deploy_artifact_no_versions(deploy_client, artifact_without_versions):
    response = deploy_client.post(
        f"/{artifact_without_versions.id}/deploy",
        json={"token": "test_token", "platform": "vercel"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Artifact has no versions to deploy."


@pytest.mark.asyncio
async def test_deploy_preflight_rejects_tsx_only(deploy_client, mock_artifact):
    with patch(
        "app.api.files.deploy_api.run_deploy_preflight",
        new_callable=AsyncMock,
    ) as mock_preflight:
        from app.services.deploy.preflight import DeployPreflightResult

        mock_preflight.return_value = DeployPreflightResult(
            deployable=False,
            reason="CODE_REQUIRES_HTML_ARTIFACT",
            message="React/code artifacts must be exported as a complete index.html before deploy.",
            hint="Ask the agent to output a full HTML document artifact (type html), then deploy.",
        )
        response = deploy_client.get(f"/{mock_artifact.id}/deploy/preflight")
    assert response.status_code == 200
    data = response.json()
    assert data["deployable"] is False
    assert data["reason"] == "CODE_REQUIRES_HTML_ARTIFACT"


@pytest.mark.asyncio
async def test_deploy_vercel_failure_sets_error_status(deploy_client, mock_artifact, db_session):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.deploy = AsyncMock(side_effect=Exception("Invalid token"))

                response = deploy_client.post(
                    f"/{mock_artifact.id}/deploy",
                    json={"token": "bad_token", "platform": "vercel"},
                )

                assert response.status_code == 500
                await db_session.refresh(mock_artifact)
                assert mock_artifact.deployment_status == "ERROR"


@pytest.mark.asyncio
async def test_deploy_directory_artifact(deploy_client, mock_artifact, db_session):
    files = {
        "index.html": DeployFile(path="index.html", content="<h1>Dir</h1>"),
        "style.css": DeployFile(path="style.css", content="body{}"),
    }
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.deploy = AsyncMock(
                    return_value={
                        "deployment_id": "dep_dir",
                        "url": "https://dir.vercel.app",
                        "project_id": "prj_dir",
                        "status": "READY",
                    }
                )

                response = deploy_client.post(
                    f"/{mock_artifact.id}/deploy",
                    json={"token": "test_token", "platform": "vercel"},
                )

                assert response.status_code == 200
                call_kwargs = mock_vercel_instance.deploy.call_args.kwargs
                assert "index.html" in call_kwargs["files"]
                assert "style.css" in call_kwargs["files"]


@pytest.mark.asyncio
async def test_deployment_status_ws_auth_success(deploy_client, db_session):
    @asynccontextmanager
    async def session_override():
        yield db_session

    with patch("app.api.files.deploy_api.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ({"token": "test_token"}, False)
        mock_service.decrypt.return_value = {"token": "test_token"}

        deploy_client.put(
            "/deploy/credentials/vercel",
            json={"token": "test_token"},
        )

        with patch("app.api.files.deploy_api.get_session", session_override):
            with patch("app.api.files.deploy_api._apply_deployment_state", new_callable=AsyncMock):
                with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                    mock_vercel_instance = mock_vercel_class.return_value
                    mock_vercel_instance.get_deployment_status = AsyncMock(
                        return_value={"id": "dep_123", "url": "https://test.vercel.app", "status": "READY"}
                    )

                    artifact_id = str(uuid.uuid4())
                    artifact = Artifact(id=artifact_id, name="ws-artifact", is_deleted=False)
                    db_session.add(artifact)
                    await db_session.commit()

                    with deploy_client.websocket_connect(
                        f"/{artifact_id}/deploy/status/dep_123"
                    ) as ws:
                        ws.send_json({"type": "auth"})
                        data = ws.receive_json()
                        assert data["status"] == "READY"
                    mock_vercel_class.assert_called_once_with(token="test_token")


def test_deployment_status_ws_invalid_auth_payload(deploy_client):
    artifact_id = str(uuid.uuid4())
    with deploy_client.websocket_connect(
        f"/{artifact_id}/deploy/status/dep_123"
    ) as ws:
        ws.send_json({"type": "invalid"})
        with pytest.raises(Exception, match=".*"):
            ws.receive_json()


def test_deployment_status_ws_missing_credentials(deploy_client, db_session):
    @asynccontextmanager
    async def session_override():
        yield db_session

    with patch("app.api.files.deploy_api.get_session", session_override):
        with patch("app.api.files.deploy_api._get_platform_vercel_token", return_value=None):
            artifact_id = str(uuid.uuid4())
            with deploy_client.websocket_connect(
                f"/{artifact_id}/deploy/status/dep_123"
            ) as ws:
                ws.send_json({"type": "auth"})
                with pytest.raises(Exception, match=".*"):
                    ws.receive_json()


def test_get_vercel_credentials_empty(deploy_client):
    response = deploy_client.get("/deploy/credentials/vercel")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["token"] is None
    assert data["platform_available"] is False


def test_save_and_get_vercel_credentials(deploy_client):
    with patch("app.api.files.deploy_api.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ({"token": "secret-token"}, False)
        mock_service.decrypt.return_value = {"token": "secret-token"}

        save_response = deploy_client.put(
            "/deploy/credentials/vercel",
            json={"token": "secret-token"},
        )
        assert save_response.status_code == 200

        get_response = deploy_client.get("/deploy/credentials/vercel")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["configured"] is True
        assert data["token"] == "secret-token"


@pytest.mark.asyncio
async def test_deploy_uses_stored_credentials_when_token_empty(
    deploy_client, mock_artifact, db_session
):
    with patch("app.api.files.deploy_api.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ({"token": "stored-token"}, False)
        mock_service.decrypt.return_value = {"token": "stored-token"}

        deploy_client.put("/deploy/credentials/vercel", json={"token": "stored-token"})

    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
            mock_vercel_instance = mock_vercel_class.return_value
            mock_vercel_instance.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dep_stored",
                    "url": "https://stored.vercel.app",
                    "status": "READY",
                    "project_id": "prj_stored",
                }
            )
            response = deploy_client.post(
                f"/{mock_artifact.id}/deploy",
                json={"token": "", "platform": "vercel"},
            )
            assert response.status_code == 200
            mock_vercel_class.assert_called_once_with(token="stored-token")


@pytest.mark.asyncio
async def test_deploy_passes_project_id_on_redeploy(deploy_client, mock_artifact, db_session):
    mock_artifact.deployment_project_id = "prj_existing"
    await db_session.commit()

    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
            mock_vercel_instance = mock_vercel_class.return_value
            mock_vercel_instance.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dep_re",
                    "url": "https://re.vercel.app",
                    "project_id": "prj_existing",
                    "status": "READY",
                }
            )
            response = deploy_client.post(
                f"/{mock_artifact.id}/deploy",
                json={"token": "test_token", "platform": "vercel"},
            )
            assert response.status_code == 200
            assert mock_vercel_instance.deploy.call_args.kwargs["project_id"] == "prj_existing"


@pytest.mark.asyncio
async def test_deploy_uses_platform_token_in_sandbox(deploy_client, mock_artifact):
    files = {"index.html": DeployFile(path="index.html", content="<h1>Hello</h1>")}
    with patch("app.api.files.deploy_api._get_platform_vercel_token", return_value="platform-token"):
        with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
            with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                    mock_vercel_instance = mock_vercel_class.return_value
                    mock_vercel_instance.deploy = AsyncMock(
                        return_value={
                            "deployment_id": "dep_platform",
                            "url": "https://platform.vercel.app",
                            "status": "READY",
                            "project_id": "prj_platform",
                        }
                    )

                    response = deploy_client.post(
                        f"/{mock_artifact.id}/deploy",
                        json={"token": "", "platform": "vercel"},
                    )

                    assert response.status_code == 200
                    mock_vercel_class.assert_called_once_with(token="platform-token")
