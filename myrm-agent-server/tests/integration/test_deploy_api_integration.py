"""Deploy API integration tests — real DB, vault, credentials; Vercel HTTP only mocked."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.artifacts.listener import upsert_processor_artifact
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact
from tests.support.minimal_app import API_PREFIX, build_minimal_app

_DEPLOY_BASE = f"{API_PREFIX}/files/artifacts"


@pytest.fixture(autouse=True)
def _local_deploy_mode() -> None:
    """Use local encryption service (real encrypt/decrypt, not mocked)."""
    original = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    import app.services.config.encryption as enc_mod

    enc_mod._encryption_service = None
    yield
    enc_mod._encryption_service = None
    if original:
        os.environ["DEPLOY_MODE"] = original
    else:
        os.environ.pop("DEPLOY_MODE", None)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    db_id = uuid.uuid4().hex
    engine = create_async_engine(
        f"sqlite+aiosqlite:///file:deploy_int_{db_id}?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def deploy_client(db_session: AsyncSession, tmp_path, monkeypatch: pytest.MonkeyPatch):
    limiter.enabled = False
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    app = build_minimal_app(preset="files")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.api.files.deploy_api.get_workspace_root", lambda: workspace)

    with TestClient(app) as client:
        yield client, workspace, db_session

    limiter.enabled = True
    app.dependency_overrides.clear()


async def _seed_artifact(
    db: AsyncSession,
    workspace,
    *,
    name: str = "index.html",
    content: str = "<html><body>integration deploy</body></html>",
    with_version: bool = True,
) -> str:
    art_id = str(uuid.uuid4())
    if not with_version:
        artifact = Artifact(id=art_id, name=name, is_deleted=False)
        db.add(artifact)
        await db.commit()
        return art_id

    html_path = workspace / name
    html_path.write_text(content, encoding="utf-8")
    await upsert_processor_artifact(
        db,
        file_id=art_id,
        filename=name,
        sandbox_path=str(html_path),
        workspace_root=str(workspace),
        chat_id=f"chat-{art_id[:8]}",
    )
    return art_id


class TestDeployPreflightIntegration:
    @pytest.mark.asyncio
    async def test_preflight_ok_for_html_artifact(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        resp = client.get(f"{_DEPLOY_BASE}/{art_id}/deploy/preflight")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deployable"] is True
        assert body["reason"] == "OK"

    @pytest.mark.asyncio
    async def test_preflight_rejects_non_html_artifact(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(
            db,
            workspace,
            name="App.tsx",
            content="export default function App() { return null; }",
        )

        resp = client.get(f"{_DEPLOY_BASE}/{art_id}/deploy/preflight")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deployable"] is False
        # Vault single-object path has no .tsx suffix on disk → REQUIRES_HTML_ENTRY
        assert body["reason"] in ("CODE_REQUIRES_HTML_ARTIFACT", "REQUIRES_HTML_ENTRY")

    @pytest.mark.asyncio
    async def test_preflight_no_versions(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace, with_version=False)

        resp = client.get(f"{_DEPLOY_BASE}/{art_id}/deploy/preflight")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deployable"] is False
        assert body["reason"] == "NO_VERSIONS"


class TestDeployPostIntegration:
    @pytest.mark.asyncio
    async def test_post_deploy_full_chain_mocks_vercel_only(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        with patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class:
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_integration",
                    "url": "https://integration-test.vercel.app",
                    "project_id": "prj_integration",
                    "status": "READY",
                }
            )

            resp = client.post(
                f"{_DEPLOY_BASE}/{art_id}/deploy",
                json={"token": "inline-token", "platform": "vercel"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://integration-test.vercel.app"
        assert data["deployment_id"] == "dpl_integration"
        assert data["latest_version_id"] is not None
        mock_vercel_class.assert_called_once_with(token="inline-token")
        deploy_kwargs = mock_vercel.deploy.call_args.kwargs
        assert "index.html" in deploy_kwargs["files"]

    @pytest.mark.asyncio
    async def test_post_deploy_no_versions_400(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace, with_version=False)

        resp = client.post(
            f"{_DEPLOY_BASE}/{art_id}/deploy",
            json={"token": "tok", "platform": "vercel"},
        )
        assert resp.status_code == 400
        assert "no versions" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_post_deploy_uses_stored_credentials(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        client.put(
            f"{_DEPLOY_BASE}/deploy/credentials/vercel",
            json={"token": "stored-integration-token"},
        )

        with patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class:
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_stored",
                    "url": "https://stored.vercel.app",
                    "project_id": "prj_stored",
                    "status": "READY",
                }
            )

            resp = client.post(
                f"{_DEPLOY_BASE}/{art_id}/deploy",
                json={"token": "", "platform": "vercel"},
            )

        assert resp.status_code == 200
        mock_vercel_class.assert_called_once_with(token="stored-integration-token")

    @pytest.mark.asyncio
    async def test_post_deploy_vercel_failure_sets_error_status(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        with patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class:
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(side_effect=RuntimeError("Vercel rejected token"))

            resp = client.post(
                f"{_DEPLOY_BASE}/{art_id}/deploy",
                json={"token": "bad-token", "platform": "vercel"},
            )

        assert resp.status_code == 500
        from sqlalchemy import select

        row = (await db.execute(select(Artifact).where(Artifact.id == art_id))).scalar_one()
        assert row.deployment_status == "ERROR"


class TestAgentDeployServiceIntegration:
    @pytest.mark.asyncio
    async def test_agent_execute_deploy_shares_executor(self, deploy_client) -> None:
        _, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        @asynccontextmanager
        async def session_override():
            yield db

        with (
            patch("app.database.connection.get_session", session_override),
            patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class,
        ):
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_agent",
                    "url": "https://agent-path.vercel.app",
                    "project_id": "prj_agent",
                    "status": "READY",
                }
            )

            from app.services.deploy.agent_deploy_service import AgentDeployService
            from app.services.deploy.credentials import save_vercel_credentials

            await save_vercel_credentials(db, "agent-svc-token")
            svc = AgentDeployService(workspace_root=str(workspace))
            result = await svc.execute_deploy(art_id)

        assert result.success is True
        assert result.url == "https://agent-path.vercel.app"
        mock_vercel_class.assert_called_once_with(token="agent-svc-token")


class TestDeployCredentialsIntegration:
    def test_credentials_save_and_load_roundtrip(self, deploy_client) -> None:
        client, _, _ = deploy_client
        token = "integration-vercel-token-xyz"

        save_resp = client.put(f"{_DEPLOY_BASE}/deploy/credentials/vercel", json={"token": token})
        assert save_resp.status_code == 200

        get_resp = client.get(f"{_DEPLOY_BASE}/deploy/credentials/vercel")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["configured"] is True
        assert data["token"] == token

    def test_credentials_update_overwrites_previous(self, deploy_client) -> None:
        client, _, _ = deploy_client
        client.put(f"{_DEPLOY_BASE}/deploy/credentials/vercel", json={"token": "first-token"})
        client.put(f"{_DEPLOY_BASE}/deploy/credentials/vercel", json={"token": "second-token"})

        get_resp = client.get(f"{_DEPLOY_BASE}/deploy/credentials/vercel")
        assert get_resp.json()["token"] == "second-token"

    def test_credentials_empty_when_unconfigured(self, deploy_client) -> None:
        client, _, _ = deploy_client
        resp = client.get(f"{_DEPLOY_BASE}/deploy/credentials/vercel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["token"] is None


class TestDeployApiEdgeCases:
    def test_post_artifact_not_found(self, deploy_client) -> None:
        client, _, _ = deploy_client
        resp = client.post(
            f"{_DEPLOY_BASE}/{uuid.uuid4()}/deploy",
            json={"token": "tok", "platform": "vercel"},
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    def test_post_unsupported_platform(self, deploy_client) -> None:
        client, _, _ = deploy_client
        resp = client.post(
            f"{_DEPLOY_BASE}/{uuid.uuid4()}/deploy",
            json={"token": "tok", "platform": "netlify"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Only Vercel is supported currently"

    def test_post_missing_token_without_stored_credentials(self, deploy_client) -> None:
        client, _, _ = deploy_client
        resp = client.post(
            f"{_DEPLOY_BASE}/{uuid.uuid4()}/deploy",
            json={"token": "", "platform": "vercel"},
        )
        assert resp.status_code == 400
        assert "token is required" in resp.json()["detail"].lower()

    def test_preflight_artifact_not_found(self, deploy_client) -> None:
        client, _, _ = deploy_client
        resp = client.get(f"{_DEPLOY_BASE}/{uuid.uuid4()}/deploy/preflight")
        assert resp.status_code == 200
        body = resp.json()
        assert body["deployable"] is False
        assert body["reason"] == "PACKAGING_ERROR"


class TestDeployModalParityIntegration:
    """DeployModal sends POST with platform only (token from stored credentials)."""

    @pytest.mark.asyncio
    async def test_post_deploy_modal_payload_shape(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)
        client.put(
            f"{_DEPLOY_BASE}/deploy/credentials/vercel",
            json={"token": "modal-flow-token"},
        )

        with patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class:
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_modal",
                    "url": "https://modal-flow.vercel.app",
                    "project_id": "prj_modal",
                    "status": "READY",
                }
            )
            resp = client.post(
                f"{_DEPLOY_BASE}/{art_id}/deploy",
                json={"platform": "vercel"},
            )

        assert resp.status_code == 200
        assert resp.json()["deployment_id"] == "dpl_modal"
        mock_vercel_class.assert_called_once_with(token="modal-flow-token")

    @pytest.mark.asyncio
    async def test_redeploy_passes_existing_project_id(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)
        artifact = (await db.get(Artifact, art_id))
        assert artifact is not None
        artifact.deployment_project_id = "prj_existing"
        await db.commit()

        with patch("app.services.deploy.vercel_client.VercelClient") as mock_vercel_class:
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dpl_re",
                    "url": "https://re.vercel.app",
                    "project_id": "prj_existing",
                    "status": "READY",
                }
            )
            resp = client.post(
                f"{_DEPLOY_BASE}/{art_id}/deploy",
                json={"token": "tok", "platform": "vercel"},
            )

        assert resp.status_code == 200
        assert mock_vercel.deploy.call_args.kwargs["project_id"] == "prj_existing"


class TestDeployWebSocketIntegration:
    @pytest.mark.asyncio
    async def test_websocket_status_auth_success(self, deploy_client) -> None:
        client, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)
        client.put(
            f"{_DEPLOY_BASE}/deploy/credentials/vercel",
            json={"token": "ws-integration-token"},
        )

        @asynccontextmanager
        async def session_override():
            yield db

        with (
            patch("app.api.files.deploy_api.get_session", session_override),
            patch("app.api.files.deploy_api._apply_deployment_state", new_callable=AsyncMock),
            patch("app.api.files.deploy_api.VercelClient") as mock_vercel_class,
        ):
            mock_vercel = mock_vercel_class.return_value
            mock_vercel.get_deployment_status = AsyncMock(
                return_value={"id": "dep_ws", "url": "https://ws.vercel.app", "status": "READY"}
            )

            with client.websocket_connect(f"{_DEPLOY_BASE}/{art_id}/deploy/status/dep_ws") as ws:
                ws.send_json({"type": "auth"})
                data = ws.receive_json()
                assert data["status"] == "READY"
            mock_vercel_class.assert_called_once_with(token="ws-integration-token")


class TestAgentDeployServiceIntegrationExtended:
    @pytest.mark.asyncio
    async def test_agent_preflight_real(self, deploy_client) -> None:
        _, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        @asynccontextmanager
        async def session_override():
            yield db

        with patch("app.database.connection.get_session", session_override):
            from app.services.deploy.agent_deploy_service import AgentDeployService

            svc = AgentDeployService(workspace_root=str(workspace))
            deployable, message = await svc.preflight(art_id)

        assert deployable is True
        assert "ready" in message.lower()

    @pytest.mark.asyncio
    async def test_agent_execute_token_missing(self, deploy_client) -> None:
        _, workspace, db = deploy_client
        art_id = await _seed_artifact(db, workspace)

        @asynccontextmanager
        async def session_override():
            yield db

        with patch("app.database.connection.get_session", session_override):
            from app.services.deploy.agent_deploy_service import AgentDeployService

            svc = AgentDeployService(workspace_root=str(workspace))
            result = await svc.execute_deploy(art_id)

        assert result.success is False
        assert result.status == "TOKEN_MISSING"

