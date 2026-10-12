"""Unit and integration tests for Artifact Provenance Hub and cross-session retrieval API."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactAuditLog, ArtifactVersion
from app.database.models.chat import Chat


@pytest.mark.asyncio
async def test_list_artifact_provenance_empty(client: TestClient, db_session: AsyncSession) -> None:
    """Verify empty provenance response returns zero total and zeroed category stats."""
    response = client.get("/api/v1/files/artifacts/provenance")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["stats"]["all"] == 0
    assert data["stats"]["document"] == 0
    assert data["stats"]["code"] == 0


@pytest.mark.asyncio
async def test_list_artifact_provenance_categories_and_filters(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    """Verify multi-category classification, category stats, and search filtering across chats."""
    # 1. Setup Chat sessions
    chat1 = Chat(id="chat-alpha", title="Quarterly Financial Audit", agent_id="analyst-agent")
    chat2 = Chat(id="chat-beta", title="Core Engine Refactor", agent_id="engineer-agent")
    db_session.add_all([chat1, chat2])
    await db_session.flush()

    # 2. Setup Artifacts across different categories
    art_doc = Artifact(id="art-doc-1", name="audit_report.pdf", description="Q3 Audit Report", chat_id="chat-alpha")
    art_code = Artifact(id="art-code-1", name="data_pipeline.py", description="ETL pipeline script", chat_id="chat-beta")
    art_data = Artifact(id="art-data-1", name="transactions.csv", description="Ledger entries", chat_id="chat-alpha")
    art_media = Artifact(id="art-media-1", name="topology.png", description="System architecture diagram", chat_id="chat-beta")
    art_link = Artifact(id="art-link-1", name="https://docs.kernel.org/consensus", description="External RFC link", chat_id="chat-beta")
    db_session.add_all([art_doc, art_code, art_data, art_media, art_link])
    await db_session.flush()

    # 3. Add versions
    ver1 = ArtifactVersion(
        id="ver-1",
        artifact_id="art-doc-1",
        vault_uri="vault://dummy-doc",
        sha256_hash=hashlib.sha256(b"dummy doc").hexdigest(),
        commit_message="Initial draft",
    )
    ver2 = ArtifactVersion(
        id="ver-2",
        artifact_id="art-code-1",
        vault_uri="vault://dummy-code",
        sha256_hash=hashlib.sha256(b"dummy code").hexdigest(),
        commit_message="Refactor ETL logic",
    )
    db_session.add_all([ver1, ver2])
    await db_session.commit()

    # 4. Query all provenance items
    res_all = client.get("/api/v1/files/artifacts/provenance")
    assert res_all.status_code == 200
    all_data = res_all.json()
    assert all_data["total"] == 5
    assert all_data["stats"]["all"] == 5
    assert all_data["stats"]["document"] == 1
    assert all_data["stats"]["code"] == 1
    assert all_data["stats"]["data"] == 1
    assert all_data["stats"]["media"] == 1
    assert all_data["stats"]["link"] == 1

    # Check bidirectional association
    first_item = next(it for it in all_data["items"] if it["id"] == "art-doc-1")
    assert first_item["category"] == "document"
    assert first_item["chat_id"] == "chat-alpha"
    assert first_item["chat_title"] == "Quarterly Financial Audit"
    assert first_item["agent_id"] == "analyst-agent"
    assert first_item["latest_version_id"] == "ver-1"
    assert first_item["commit_message"] == "Initial draft"

    # 5. Filter by category
    res_code = client.get("/api/v1/files/artifacts/provenance?category=code")
    assert res_code.status_code == 200
    code_data = res_code.json()
    assert code_data["total"] == 1
    assert code_data["items"][0]["id"] == "art-code-1"

    # 6. Filter by query
    res_search = client.get("/api/v1/files/artifacts/provenance?query=transactions")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["id"] == "art-data-1"

    # 7. Filter by chat_id
    res_chat = client.get("/api/v1/files/artifacts/provenance?chat_id=chat-alpha")
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert chat_data["total"] == 2


@pytest.mark.asyncio
async def test_get_artifact_provenance_detail(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    """Verify single artifact bidirectional provenance graph and version evolution timeline."""
    chat = Chat(id="chat-gamma", title="Research Investigation", agent_id="researcher")
    db_session.add(chat)
    await db_session.flush()

    art = Artifact(id="art-detail-1", name="spec.md", description="System specification", chat_id="chat-gamma")
    db_session.add(art)
    await db_session.flush()

    v1 = ArtifactVersion(
        id="v-1",
        artifact_id="art-detail-1",
        vault_uri="vault://v1",
        sha256_hash=hashlib.sha256(b"v1").hexdigest(),
        commit_message="Initial specification",
    )
    v2 = ArtifactVersion(
        id="v-2",
        artifact_id="art-detail-1",
        vault_uri="vault://v2",
        sha256_hash=hashlib.sha256(b"v2").hexdigest(),
        commit_message="Add concurrency model",
    )
    audit = ArtifactAuditLog(
        artifact_id="art-detail-1",
        action="UPDATE",
        user_id="usr-1",
    )
    db_session.add_all([v1, v2, audit])
    await db_session.commit()

    # Query detail
    res = client.get("/api/v1/files/artifacts/provenance/art-detail-1")
    assert res.status_code == 200
    detail = res.json()
    assert detail["artifact"]["id"] == "art-detail-1"
    assert detail["artifact"]["chat_title"] == "Research Investigation"
    assert len(detail["versions"]) == 2
    assert detail["audit_logs_count"] == 1

    # 404 for missing
    res_missing = client.get("/api/v1/files/artifacts/provenance/art-nonexistent")
    assert res_missing.status_code == 404
