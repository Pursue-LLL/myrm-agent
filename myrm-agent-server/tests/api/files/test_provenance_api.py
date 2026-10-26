"""Provenance sizes come from the vault of the chat that produced each artifact."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion
from tests.support.chat_workspace import chats_bound_to_workspaces

_BASE = "/api/v1/files/artifacts/provenance"


async def _seed_artifact(db_session: AsyncSession, *, artifact_id: str, chat_id: str, workspace: Path, size: int) -> None:
    vault_uri = ArtifactVault(str(workspace)).put("x" * size, f"{artifact_id}.txt")
    db_session.add(Artifact(id=artifact_id, name=f"{artifact_id}.txt", chat_id=chat_id))
    await db_session.flush()
    db_session.add(ArtifactVersion(id=f"ver-{artifact_id}", artifact_id=artifact_id, vault_uri=vault_uri, sha256_hash="h"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_list_reports_each_artifact_size_from_its_own_chat_workspace(
    client: TestClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    workspaces = {"chat-a": tmp_path / "ws_a", "chat-b": tmp_path / "ws_b"}
    await _seed_artifact(db_session, artifact_id="art-a", chat_id="chat-a", workspace=workspaces["chat-a"], size=11)
    await _seed_artifact(db_session, artifact_id="art-b", chat_id="chat-b", workspace=workspaces["chat-b"], size=22)

    with chats_bound_to_workspaces(workspaces):
        response = client.get(_BASE)

    assert response.status_code == 200
    sizes = {item["id"]: item["size_bytes"] for item in response.json()["items"]}
    assert sizes == {"art-a": 11, "art-b": 22}


@pytest.mark.asyncio
async def test_detail_reports_version_sizes_from_the_artifact_chat_workspace(
    client: TestClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    workspace = tmp_path / "ws_detail"
    await _seed_artifact(db_session, artifact_id="art-d", chat_id="chat-d", workspace=workspace, size=33)

    with chats_bound_to_workspaces({"chat-d": workspace}):
        response = client.get(f"{_BASE}/art-d")

    assert response.status_code == 200
    body = response.json()
    assert body["artifact"]["size_bytes"] == 33
    assert [v["size_bytes"] for v in body["versions"]] == [33]
