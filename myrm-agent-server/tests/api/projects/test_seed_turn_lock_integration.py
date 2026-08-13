"""Tests for the local-only project turn-lock seed endpoint.

Validates the deterministic lock-holding fixture used by the Chrome E2E:
1. Creates a project + chat and binds the chat to the project
2. Acquires the project lock before returning (is_locked() is true)
3. Releases the lock automatically after `hold_ms`
4. Validates hold_ms bounds and local-mode gating
"""

from __future__ import annotations

import asyncio

import pytest

from app.api.projects.test_fixtures import release_turn_lock, seed_turn_lock
from app.database.dto import ChatCreate
from app.services.project.orchestrator import ProjectOrchestrator


@pytest.mark.asyncio
async def test_seed_turn_lock_creates_bound_chat_and_holds_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def _fake_create_project(**kwargs: object) -> dict[str, object]:
        captured["project_name"] = str(kwargs["name"])
        return {"id": "e2eproject-123", "name": str(kwargs["name"])}

    async def _fake_create_or_update_chat(chat_create: ChatCreate) -> None:
        captured["chat_id"] = str(chat_create.chat_id)

    async def _fake_move_chat(chat_id: str, project_id: str | None) -> bool:
        captured["moved_chat"] = chat_id
        captured["moved_project"] = str(project_id)
        return True

    class _FakeAgent:
        id = "agent-1"

    async def _fake_agent_list(
        page: int = 1, page_size: int = 20
    ) -> tuple[list[object], int]:
        return [_FakeAgent()], 1

    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.create_project",
        _fake_create_project,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ChatService.create_or_update_chat",
        _fake_create_or_update_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.move_chat_to_project",
        _fake_move_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.AgentService.get_agent_list",
        _fake_agent_list,
    )

    # Fresh orchestrator (isolate from any global lock state)
    orch = ProjectOrchestrator()
    monkeypatch.setattr("app.services.project.orchestrator.project_orchestrator", orch)
    monkeypatch.setattr("app.api.projects.test_fixtures.project_orchestrator", orch)

    result = await seed_turn_lock(hold_ms=3000)
    assert result["chat_id"].startswith("e2eturnlock"), result
    assert str(result["project_id"]) == "e2eproject-123"
    assert result["ui_path"] == f"/{result['chat_id']}"
    assert captured["moved_chat"] == result["chat_id"]
    assert captured["moved_project"] == "e2eproject-123"

    # Lock must be held synchronously after the seed returns
    assert orch.is_locked("e2eproject-123") is True

    # ...and released automatically after hold_ms
    await asyncio.sleep(3.2)
    assert orch.is_locked("e2eproject-123") is False


@pytest.mark.asyncio
async def test_seed_turn_lock_rejects_invalid_hold_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    async def _no_agents(*_args: object, **_kwargs: object) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(
        "app.api.projects.test_fixtures.AgentService.get_agent_list",
        _no_agents,
    )

    with pytest.raises(HTTPException) as exc_info:
        await seed_turn_lock(hold_ms=-1)
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        await seed_turn_lock(hold_ms=61000)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_seed_turn_lock_none_does_not_acquire_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """hold_ms=None creates the fixture without touching the project lock.

    The E2E acquires the lock separately right before the send (immune to
    attach/bootstrap latency under heavy parallel load), so the seed must be
    able to skip locking.
    """

    async def _fake_create_project(**kwargs: object) -> dict[str, object]:
        return {"id": "e2eproject-nolock", "name": str(kwargs["name"])}

    async def _fake_create_or_update_chat(chat_create: object) -> None:
        pass

    async def _fake_move_chat(chat_id: str, project_id: str | None) -> bool:
        return True

    class _FakeAgent:
        id = "agent-1"

    async def _fake_agent_list(
        page: int = 1, page_size: int = 20
    ) -> tuple[list[object], int]:
        return [_FakeAgent()], 1

    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.create_project",
        _fake_create_project,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ChatService.create_or_update_chat",
        _fake_create_or_update_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.move_chat_to_project",
        _fake_move_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.AgentService.get_agent_list",
        _fake_agent_list,
    )

    orch = ProjectOrchestrator()
    monkeypatch.setattr("app.services.project.orchestrator.project_orchestrator", orch)
    monkeypatch.setattr("app.api.projects.test_fixtures.project_orchestrator", orch)

    result = await seed_turn_lock(hold_ms=None)
    assert str(result["project_id"]) == "e2eproject-nolock"
    assert result["hold_ms"] is None
    # No lock acquired — the fixture is inert until the test takes the lock.
    assert orch.is_locked("e2eproject-nolock") is False


@pytest.mark.asyncio
async def test_seed_turn_lock_zero_holds_until_explicit_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """hold_ms=0 acquires the lock and never auto-releases it.

    The Chrome E2E holds the lock across attach + send + cancel + re-send and
    releases it at a deterministic point via release-turn-lock, so the seed
    must not auto-expire mid-test.
    """

    async def _fake_create_project(**kwargs: object) -> dict[str, object]:
        return {"id": "e2eproject-hold", "name": str(kwargs["name"])}

    async def _fake_create_or_update_chat(chat_create: object) -> None:
        pass

    async def _fake_move_chat(chat_id: str, project_id: str | None) -> bool:
        return True

    class _FakeAgent:
        id = "agent-1"

    async def _fake_agent_list(
        page: int = 1, page_size: int = 20
    ) -> tuple[list[object], int]:
        return [_FakeAgent()], 1

    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.create_project",
        _fake_create_project,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ChatService.create_or_update_chat",
        _fake_create_or_update_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.ProjectService.move_chat_to_project",
        _fake_move_chat,
    )
    monkeypatch.setattr(
        "app.api.projects.test_fixtures.AgentService.get_agent_list",
        _fake_agent_list,
    )

    orch = ProjectOrchestrator()
    monkeypatch.setattr("app.services.project.orchestrator.project_orchestrator", orch)
    monkeypatch.setattr("app.api.projects.test_fixtures.project_orchestrator", orch)

    result = await seed_turn_lock(hold_ms=0)
    assert str(result["project_id"]) == "e2eproject-hold"
    assert result["hold_ms"] == 0
    assert orch.is_locked("e2eproject-hold") is True

    # No auto-release: the lock stays held well beyond any positive hold_ms window.
    await asyncio.sleep(1.2)
    assert orch.is_locked("e2eproject-hold") is True

    # Deterministic release via release-turn-lock.
    release_result = await release_turn_lock({"project_id": "e2eproject-hold"})
    assert release_result["ok"] is True
    assert release_result["still_locked"] is False
    assert orch.is_locked("e2eproject-hold") is False


@pytest.mark.asyncio
async def test_release_turn_lock_is_idempotent() -> None:
    """Releasing an unlocked project is a no-op (must not raise)."""
    result = await release_turn_lock({"project_id": "e2eproject-free"})
    assert result["ok"] is True
    assert result["still_locked"] is False


def test_seed_turn_lock_honors_local_mode_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    monkeypatch.setattr("app.api.projects.test_fixtures.is_local_mode", lambda: False)

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await seed_turn_lock(hold_ms=3000)
        assert exc_info.value.status_code == 404

    asyncio.run(_run())
