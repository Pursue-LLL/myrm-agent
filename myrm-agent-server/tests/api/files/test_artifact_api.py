import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from app.database.models.artifact_publication import ArtifactPublication
from app.database.models.chat import Chat
from app.database.models.project import Project
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID


@pytest.mark.asyncio
async def test_artifact_hash_verification(client: TestClient, db_session: AsyncSession, tmp_path):
    """Test that the artifact API correctly verifies the SHA-256 hash of a file."""
    # 1. Setup mock vault file
    vault_dir = tmp_path / ".agent" / "vault" / "objects"
    vault_dir.mkdir(parents=True, exist_ok=True)

    test_content = b"Hello, Enterprise Vault!"
    expected_hash = hashlib.sha256(test_content).hexdigest()

    obj_id = "test-uuid-1234"
    file_path = vault_dir / obj_id
    file_path.write_bytes(test_content)

    vault_uri = f"vault://{obj_id}"

    # 2. Insert DB records
    artifact = Artifact(id="art-1", name="Test Doc")
    db_session.add(artifact)
    await db_session.flush()

    version = ArtifactVersion(id="ver-1", artifact_id="art-1", vault_uri=vault_uri, sha256_hash=expected_hash)
    db_session.add(version)
    await db_session.commit()

    # 3. Test verification success
    # Mock get_workspace_root_sync to return tmp_path
    from unittest.mock import patch

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    with (
        patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
        patch.object(ArtifactVault, "get_object_path", return_value=file_path),
    ):
        response = client.post("/api/v1/files/artifacts/art-1/verify/ver-1")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["status"] == "TAMPER_FREE"

    # 4. Test tamper detection
    tampered_content = b"Hacked, Enterprise Vault!"
    file_path.write_bytes(tampered_content)

    with (
        patch("app.api.dependencies.get_workspace_root", return_value=tmp_path),
        patch.object(ArtifactVault, "get_object_path", return_value=file_path),
    ):
        response = client.post("/api/v1/files/artifacts/art-1/verify/ver-1")
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert data["status"] == "CORRUPTED"


@pytest.mark.asyncio
async def test_list_artifacts_includes_publications(client: TestClient, db_session: AsyncSession):
    artifact = Artifact(
        id="art-deploy-1",
        name="Landing Page",
    )
    db_session.add(artifact)
    await db_session.flush()
    db_session.add(
        ArtifactPublication(
            id=str(uuid.uuid4()),
            artifact_id="art-deploy-1",
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            publication_url="https://landing.vercel.app",
            publication_status="READY",
            publication_project_ref="prj_123",
        )
    )
    await db_session.commit()

    response = client.get("/api/v1/files/artifacts")
    assert response.status_code == 200
    data = response.json()
    assert len(data["artifacts"]) >= 1

    listed = next(item for item in data["artifacts"] if item["id"] == "art-deploy-1")
    assert len(listed["publications"]) == 1
    pub = listed["publications"][0]
    assert pub["publication_url"] == "https://landing.vercel.app"
    assert pub["publication_status"] == "READY"
    assert pub["publication_project_ref"] == "prj_123"


@pytest.mark.asyncio
async def test_list_artifacts_supports_limit_query(client: TestClient, db_session: AsyncSession):
    db_session.add(Artifact(id="art-limit-1", name="Limit One"))
    db_session.add(Artifact(id="art-limit-2", name="Limit Two"))
    await db_session.commit()

    response = client.get("/api/v1/files/artifacts?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["artifacts"]) == 1


@pytest.mark.asyncio
async def test_list_artifacts_supports_project_filter_query(client: TestClient, db_session: AsyncSession):
    db_session.add(Project(id="proj-alpha", name="Alpha"))
    db_session.add(Project(id="proj-beta", name="Beta"))
    db_session.add(Chat(id="chat-alpha", project_id="proj-alpha"))
    db_session.add(Chat(id="chat-beta", project_id="proj-beta"))
    db_session.add(Artifact(id="art-alpha", name="Alpha Artifact", chat_id="chat-alpha"))
    db_session.add(Artifact(id="art-beta", name="Beta Artifact", chat_id="chat-beta"))
    db_session.add(Artifact(id="art-global", name="Global Artifact"))
    await db_session.commit()

    response = client.get("/api/v1/files/artifacts?project_id=proj-alpha")
    assert response.status_code == 200
    data = response.json()
    listed_ids = {item["id"] for item in data["artifacts"]}
    assert listed_ids == {"art-alpha"}


@pytest.mark.asyncio
async def test_list_artifacts_returns_assessment_import_candidate_probe(
    client: TestClient,
    db_session: AsyncSession,
    tmp_path,
):
    from unittest.mock import patch

    vault_dir = tmp_path / ".agent" / "vault" / "objects"
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "obj-importable").write_text("# Milestone\n- [ ] Ship rollout", encoding="utf-8")
    (vault_dir / "obj-non-importable").write_text("Narrative summary only.", encoding="utf-8")
    (vault_dir / "obj-no-actionable").write_text("# Notes\n- notes: keep context only", encoding="utf-8")

    db_session.add(Project(id="proj-probe", name="Probe"))
    db_session.add(Chat(id="chat-probe", project_id="proj-probe"))
    db_session.add(Artifact(id="art-importable", name="Importable", chat_id="chat-probe"))
    db_session.add(Artifact(id="art-non-importable", name="Narrative", chat_id="chat-probe"))
    db_session.add(Artifact(id="art-no-actionable", name="No Actionable", chat_id="chat-probe"))
    db_session.add(
        ArtifactVersion(
            id="ver-importable",
            artifact_id="art-importable",
            vault_uri="vault://obj-importable",
            sha256_hash="sha-importable",
        )
    )
    db_session.add(
        ArtifactVersion(
            id="ver-non-importable",
            artifact_id="art-non-importable",
            vault_uri="vault://obj-non-importable",
            sha256_hash="sha-non-importable",
        )
    )
    db_session.add(
        ArtifactVersion(
            id="ver-no-actionable",
            artifact_id="art-no-actionable",
            vault_uri="vault://obj-no-actionable",
            sha256_hash="sha-no-actionable",
        )
    )
    await db_session.commit()

    with patch("app.api.files.artifact_api.get_workspace_root", return_value=tmp_path):
        response = client.get(
            "/api/v1/files/artifacts?project_id=proj-probe&assessment_import_candidate=true"
        )

    assert response.status_code == 200
    data = response.json()
    by_id = {item["id"]: item for item in data["artifacts"]}
    assert by_id["art-importable"]["assessment_import_candidate"] == {
        "status": "importable",
        "reason": None,
    }
    assert by_id["art-non-importable"]["assessment_import_candidate"] == {
        "status": "not_importable",
        "reason": "no_importable_tasks",
    }
    assert by_id["art-no-actionable"]["assessment_import_candidate"] == {
        "status": "not_importable",
        "reason": "no_actionable_tasks",
    }


@pytest.mark.asyncio
async def test_get_artifact_returns_publications(client: TestClient, db_session: AsyncSession):
    artifact = Artifact(
        id="art-get-1",
        name="Portfolio",
    )
    db_session.add(artifact)
    await db_session.flush()
    db_session.add(
        ArtifactPublication(
            id=str(uuid.uuid4()),
            artifact_id="art-get-1",
            hosting_target_id=LEGACY_VERCEL_TARGET_ID,
            publication_url="https://portfolio.vercel.app",
            publication_status="READY",
            publication_project_ref="prj_456",
        )
    )
    await db_session.commit()

    response = client.get("/api/v1/files/artifacts/art-get-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "art-get-1"
    assert len(data["publications"]) == 1
    pub = data["publications"][0]
    assert pub["publication_url"] == "https://portfolio.vercel.app"
    assert pub["publication_status"] == "READY"
    assert pub["publication_project_ref"] == "prj_456"


@pytest.mark.asyncio
async def test_get_artifact_not_found(client: TestClient):
    response = client.get("/api/v1/files/artifacts/missing-id")
    assert response.status_code == 404
