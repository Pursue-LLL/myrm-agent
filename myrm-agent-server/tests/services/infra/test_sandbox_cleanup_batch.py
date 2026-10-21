"""Cleaning many chats must scan the shared artifact vault once, not once per chat."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault, VaultObject

from app.config.settings import settings
from app.services.infra.sandbox_cleanup import cleanup_chat_workspace, cleanup_chat_workspaces


@pytest.fixture
def harness_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings.database, "harness_dir", str(tmp_path))
    return tmp_path


def _filenames(vault: ArtifactVault) -> list[str]:
    return sorted(obj.filename for obj in vault.list_objects())


@pytest.mark.asyncio
async def test_batch_cleanup_purges_the_vault_objects_of_every_chat_with_one_scan(
    harness_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = ArtifactVault(str(harness_dir))
    vault.put("a", "subagent_chat-a.md", description="output of a")
    vault.put("b", "subagent_chat-b.md", description="output of b")
    vault.put("other", "subagent_chat-other.md", description="output of another chat")

    scans = 0
    list_objects = ArtifactVault.list_objects

    def counting_list_objects(self: ArtifactVault) -> list[VaultObject]:
        nonlocal scans
        scans += 1
        return list_objects(self)

    monkeypatch.setattr(ArtifactVault, "list_objects", counting_list_objects)

    results = await cleanup_chat_workspaces(["chat-a", "chat-b"])

    assert results == {"storage_workspace": True, "artifact_vault": True}
    assert scans == 1
    assert _filenames(vault) == ["subagent_chat-other.md"]


@pytest.mark.asyncio
async def test_single_chat_cleanup_purges_the_session_vault_and_the_shared_vault(harness_dir: Path) -> None:
    shared = ArtifactVault(str(harness_dir))
    shared.put("shared", "subagent_chat-x.md", description="shared output")
    session_workspace = harness_dir / "workspaces" / "chat_chat-x"
    session_workspace.mkdir(parents=True)
    session = ArtifactVault(str(session_workspace))
    session.put("session", "report.md", description="session output")

    assert await cleanup_chat_workspace("chat-x") == {"storage_workspace": True, "artifact_vault": True}

    assert _filenames(shared) == []
    assert _filenames(session) == []


@pytest.mark.asyncio
async def test_cleaning_no_chats_touches_nothing(harness_dir: Path) -> None:
    entries_before = set(harness_dir.rglob("*"))

    assert await cleanup_chat_workspaces([]) == {"storage_workspace": True, "artifact_vault": True}

    assert set(harness_dir.rglob("*")) == entries_before


@pytest.mark.asyncio
async def test_vault_cleanup_does_not_stall_the_event_loop(harness_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A vault scan walks and unlinks files; on the loop it froze every other request for the whole purge."""

    def slow_purge(self: ArtifactVault, task_ids: object) -> int:
        time.sleep(0.5)
        return 0

    monkeypatch.setattr(ArtifactVault, "purge_by_task_ids", slow_purge)
    heartbeats = 0

    async def heartbeat() -> None:
        nonlocal heartbeats
        while True:
            await asyncio.sleep(0.01)
            heartbeats += 1

    ticker = asyncio.create_task(heartbeat())
    try:
        assert await cleanup_chat_workspaces(["chat-slow"]) == {"storage_workspace": True, "artifact_vault": True}
    finally:
        ticker.cancel()

    # 0.5 s of purge leaves room for ~50 beats; a blocked loop manages at most one.
    assert heartbeats >= 20
