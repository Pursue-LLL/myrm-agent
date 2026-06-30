import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.files.hosting_api import router as hosting_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from app.database.models.artifact_publication import ArtifactPublication
from app.services.hosting.packager import PublishFile
from app.services.hosting.preflight import DeployPreflightResult
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID, save_hosting_targets
from app.services.hosting.types import HostingTarget


async def _seed_default_vercel_target(db_session) -> None:
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


def _patch_deployable_preflight():
    return patch(
        "app.api.files.hosting_api.run_deploy_preflight",
        new_callable=AsyncMock,
        return_value=DeployPreflightResult(
            deployable=True,
            reason="OK",
            message="OK",
            hint=None,
        ),
    )


def _patch_resolve_deploy_files(artifact: Artifact, files: dict[str, PublishFile]):
    return patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(artifact, files),
    )


@pytest.fixture(autouse=True)
def bypass_rate_limit():
    with patch(
        "app.core.infra.limiter.limiter._limiter.check",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(allowed=True, retry_after_seconds=None),
    ):
        yield


@pytest.fixture
def hosting_client(db_session) -> TestClient:
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(hosting_router)

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
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://test_uri",
        sha256_hash="test_hash",
    )
    db_session.add(version)
    await db_session.commit()
    loaded = await db_session.execute(
        select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.id == artifact.id)
    )
    return loaded.scalar_one()


@pytest.mark.asyncio
async def test_publish_artifact_success(hosting_client, mock_artifact, db_session):
    await _seed_default_vercel_target(db_session)
    files = {"index.html": PublishFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.services.hosting.providers.vercel.VercelClient") as mock_vercel_class:
            mock_vercel_instance = mock_vercel_class.return_value
            mock_vercel_instance.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dep_123",
                    "url": "https://test.vercel.app",
                    "project_id": "prj_456",
                    "status": "READY",
                }
            )
            response = hosting_client.post(
                f"/{mock_artifact.id}/publish",
                json={"target_id": LEGACY_VERCEL_TARGET_ID, "token": "test_token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["provider_publication_ref"] == "dep_123"
    assert data["publication_url"] == "https://test.vercel.app"
    assert data["publication"]["id"]
    assert data["publication"]["hosting_target_id"] == LEGACY_VERCEL_TARGET_ID
    pub = (
        await db_session.execute(
            select(ArtifactPublication).where(ArtifactPublication.artifact_id == mock_artifact.id)
        )
    ).scalars().first()
    assert pub is not None
    assert pub.publication_status == "READY"


@pytest.mark.asyncio
async def test_publish_artifact_not_found(hosting_client, db_session):
    await _seed_default_vercel_target(db_session)
    with patch(
        "app.services.hosting.orchestrator.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        side_effect=LookupError("Artifact not found"),
    ):
        response = hosting_client.post(
            f"/{uuid.uuid4()}/publish",
            json={"target_id": LEGACY_VERCEL_TARGET_ID, "token": "test_token"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_publish_preflight_rejects_tsx_only(hosting_client, mock_artifact):
    with patch("app.api.files.hosting_api.run_deploy_preflight", new_callable=AsyncMock) as mock_preflight:
        mock_preflight.return_value = DeployPreflightResult(
            deployable=False,
            reason="CODE_REQUIRES_HTML_ARTIFACT",
            message="React/code artifacts must be exported as a complete index.html before deploy.",
            hint="Ask the agent to output a full HTML document artifact (type html), then deploy.",
        )
        response = hosting_client.get(f"/{mock_artifact.id}/publish/preflight")
    assert response.status_code == 200
    assert response.json()["deployable"] is False


@pytest.mark.asyncio
async def test_make_default_hosting_target(hosting_client, db_session):
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(id="t1", name="A", provider_type="vercel", config={}, is_default=True),
            HostingTarget(id="t2", name="B", provider_type="netlify", config={}, is_default=False),
        ],
    )
    response = hosting_client.post("/hosting/targets/t2/make-default")
    assert response.status_code == 200
    assert response.json()["is_default"] is True


@pytest.mark.asyncio
async def test_publish_passes_project_id_on_redeploy(hosting_client, mock_artifact, db_session):
    await _seed_default_vercel_target(db_session)
    db_session.add(
        ArtifactPublication(
            id=str(uuid.uuid4()),
            artifact_id=mock_artifact.id,
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            publication_project_ref="prj_existing",
            publication_status="READY",
        )
    )
    await db_session.commit()
    files = {"index.html": PublishFile(path="index.html", content="<h1>Hello</h1>")}
    with _patch_deployable_preflight(), _patch_resolve_deploy_files(mock_artifact, files):
        with patch("app.services.hosting.providers.vercel.VercelClient") as mock_vercel_class:
            mock_vercel_instance = mock_vercel_class.return_value
            mock_vercel_instance.deploy = AsyncMock(
                return_value={
                    "deployment_id": "dep_re",
                    "url": "https://re.vercel.app",
                    "project_id": "prj_existing",
                    "status": "READY",
                }
            )
            response = hosting_client.post(
                f"/{mock_artifact.id}/publish",
                json={"target_id": LEGACY_VERCEL_TARGET_ID, "token": "test_token"},
            )
    assert response.status_code == 200
    assert mock_vercel_instance.deploy.call_args.kwargs["project_id"] == "prj_existing"
    assert response.json()["provider_publication_ref"] == "dep_re"


@pytest.mark.asyncio
async def test_list_hosting_targets(hosting_client, db_session):
    await save_hosting_targets(
        db_session,
        [HostingTarget(id="t-list", name="Prod", provider_type="vercel", config={}, is_default=True)],
    )
    response = hosting_client.get("/hosting/targets")
    assert response.status_code == 200
    targets = response.json()["targets"]
    assert any(item["id"] == "t-list" for item in targets)


@pytest.mark.asyncio
async def test_create_and_delete_hosting_target(hosting_client, db_session):
    create = hosting_client.post(
        "/hosting/targets",
        json={"name": "Webhook", "provider_type": "http_webhook", "config": {"webhook_url": "https://example.com/hook"}},
    )
    assert create.status_code == 200
    target_id = create.json()["id"]
    delete = hosting_client.delete(f"/hosting/targets/{target_id}")
    assert delete.status_code == 200


@pytest.mark.asyncio
async def test_get_artifact_publications(hosting_client, mock_artifact, db_session):
    await _seed_default_vercel_target(db_session)
    db_session.add(
        ArtifactPublication(
            id=str(uuid.uuid4()),
            artifact_id=mock_artifact.id,
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            publication_url="https://live.example.com",
            publication_status="READY",
        )
    )
    await db_session.commit()
    response = hosting_client.get(f"/{mock_artifact.id}/publications")
    assert response.status_code == 200
    pubs = response.json()["publications"]
    assert len(pubs) == 1
    assert pubs[0]["publication_url"] == "https://live.example.com"
