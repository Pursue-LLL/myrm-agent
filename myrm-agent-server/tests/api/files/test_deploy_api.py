import builtins
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.files.deploy_api import router as deploy_router
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion


@pytest.fixture
def deploy_client(db_session) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(deploy_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client


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
        vault_uri="test_uri",
        sha256_hash="test_hash",
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)

    return artifact


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
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.suffix = ".html"

    original_open = builtins.open

    def side_effect(filename, *args, **kwargs):
        if str(filename).endswith(".html"):
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.return_value = "<h1>Hello</h1>"
            return mock_file
        return original_open(filename, *args, **kwargs)

    with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
        mock_vault_class.return_value.get_object_path.return_value = mock_path

        with patch("builtins.open", side_effect=side_effect):
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

                await db_session.refresh(mock_artifact)
                assert mock_artifact.deployment_url == "https://test.vercel.app"
                assert mock_artifact.deployment_status == "READY"


@pytest.mark.asyncio
async def test_deploy_artifact_not_found(deploy_client):
    response = deploy_client.post(
        f"/{uuid.uuid4()}/deploy",
        json={"token": "test_token", "platform": "vercel"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


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
    assert response.json()["detail"] == "Artifact has no versions to deploy"


@pytest.mark.asyncio
async def test_deploy_vercel_failure_sets_error_status(deploy_client, mock_artifact, db_session):
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.suffix = ".html"

    with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
        mock_vault_class.return_value.get_object_path.return_value = mock_path

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.return_value = "<h1>Hello</h1>"
            mock_open.return_value = mock_file

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
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = False
    mock_path.is_dir.return_value = True

    file1 = MagicMock()
    file1.is_file.return_value = True
    file1.relative_to.return_value.as_posix.return_value = "index.html"

    file2 = MagicMock()
    file2.is_file.return_value = True
    file2.relative_to.return_value.as_posix.return_value = "style.css"

    mock_path.rglob.return_value = [file1, file2]

    with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
        mock_vault_class.return_value.get_object_path.return_value = mock_path

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.side_effect = ["<h1>Dir</h1>", "body{}"]
            mock_open.return_value = mock_file

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


def test_deployment_status_ws_auth_success(deploy_client, db_session):
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
            with patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class:
                mock_vercel_instance = mock_vercel_class.return_value
                mock_vercel_instance.get_deployment_status = AsyncMock(
                    return_value={"id": "dep_123", "url": "https://test.vercel.app", "status": "READY"}
                )

                artifact_id = str(uuid.uuid4())
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
        with pytest.raises(Exception):
            ws.receive_json()


def test_deployment_status_ws_missing_credentials(deploy_client, db_session):
    @asynccontextmanager
    async def session_override():
        yield db_session

    with patch("app.api.files.deploy_api.get_session", session_override):
        artifact_id = str(uuid.uuid4())
        with deploy_client.websocket_connect(
            f"/{artifact_id}/deploy/status/dep_123"
        ) as ws:
            ws.send_json({"type": "auth"})
            with pytest.raises(Exception):
                ws.receive_json()


def test_get_vercel_credentials_empty(deploy_client):
    response = deploy_client.get("/deploy/credentials/vercel")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["token"] is None


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

    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.suffix = ".html"

    with patch("app.api.files.deploy_api.ArtifactVault") as mock_vault_class:
        mock_vault_class.return_value.get_object_path.return_value = mock_path

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.return_value = "<h1>Hello</h1>"
            mock_open.return_value = mock_file

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
