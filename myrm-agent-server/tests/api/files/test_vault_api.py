"""Vault object reads resolve the workspace of the chat that wrote the object."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.api.files.vault_api import router as vault_router
from app.database.connection import get_db
from app.database.models.artifact import Artifact, ArtifactVersion
from tests.support.chat_workspace import chats_bound_to_workspaces

_PAYLOAD = "vault payload " * 50


@pytest.fixture
def default_root(tmp_path: Path) -> Path:
    root = tmp_path / "default_root"
    root.mkdir()
    return root


@pytest.fixture
def vault_client(db_session: AsyncSession, default_root: Path) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(vault_router, prefix="/vault")

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_workspace_root] = lambda: default_root
    with TestClient(app) as client:
        yield client


def _spill(workspace: Path) -> str:
    return ArtifactVault(str(workspace)).put(_PAYLOAD, "spill.txt", "text/plain").removeprefix("vault://")


def test_reads_the_object_from_the_workspace_of_the_named_chat(vault_client: TestClient, tmp_path: Path) -> None:
    chat_workspace = tmp_path / "chat_workspace"
    obj_id = _spill(chat_workspace)

    with chats_bound_to_workspaces({"chat-1": chat_workspace}):
        meta = vault_client.get(f"/vault/{obj_id}/meta", params={"chat_id": "chat-1"})
        content = vault_client.get(f"/vault/{obj_id}/content", params={"chat_id": "chat-1"})

    assert meta.status_code == 200
    assert meta.json()["filename"] == "spill.txt"
    assert content.status_code == 200
    assert content.text == _PAYLOAD


async def test_finds_an_artifact_object_through_the_chat_that_owns_the_artifact(
    vault_client: TestClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    chat_workspace = tmp_path / "chat_workspace"
    obj_id = _spill(chat_workspace)
    db_session.add(Artifact(id="art-v", name="spill.txt", chat_id="chat-owner"))
    await db_session.flush()
    db_session.add(ArtifactVersion(id="ver-v", artifact_id="art-v", vault_uri=f"vault://{obj_id}", sha256_hash="x"))
    await db_session.commit()

    with chats_bound_to_workspaces({"chat-owner": chat_workspace}):
        response = vault_client.get(f"/vault/{obj_id}/content")

    assert response.status_code == 200
    assert response.text == _PAYLOAD


def test_an_object_that_belongs_to_no_known_chat_is_looked_up_under_the_default_root(
    vault_client: TestClient, default_root: Path
) -> None:
    obj_id = _spill(default_root)

    response = vault_client.get(f"/vault/{obj_id}/content")

    assert response.status_code == 200
    assert response.text == _PAYLOAD


def test_a_missing_object_is_reported_not_found(vault_client: TestClient, tmp_path: Path) -> None:
    chat_workspace = tmp_path / "chat_workspace"
    chat_workspace.mkdir()

    with chats_bound_to_workspaces({"chat-1": chat_workspace}):
        response = vault_client.get("/vault/missing/meta", params={"chat_id": "chat-1"})

    assert response.status_code == 404
    assert not (chat_workspace / ".agent").exists()
