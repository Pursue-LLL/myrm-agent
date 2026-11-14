"""A prewarmed memory brief serves one turn; every later turn is built from the store as it is then.

A rule the user changes (in this chat, another chat or the memory page) has to reach the next turn of a chat that
already ran: handing that turn the first turn's memory block would keep the stale rule in force.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

from app.core.memory.adapters import setup as memory_setup
from app.services.agent.execution_cache.prewarm.brief_cache import BriefCache
from app.services.agent.execution_cache.prewarm.coordinator import TurnPrewarmCoordinator

_AGENT_ID = "agent-default"
_CHAT_ID = "chat-1"
_COORDINATOR = "app.services.agent.execution_cache.prewarm.coordinator"
# A build is a couple of milliseconds; the turn's join budget is not what these tests are about.
_JOIN_BUDGET_SECONDS = 5.0


def _params() -> SimpleNamespace:
    return SimpleNamespace(
        enable_memory=True,
        incognito_mode=False,
        embedding_config=None,
        memory_conversation_id=_CHAT_ID,
        chat_id=_CHAT_ID,
        agent_id=_AGENT_ID,
        memory_channel_id=None,
        channel_name=None,
        memory_task_id=None,
        memory_shared_context_ids=[],
        memory_policy=None,
        memory_require_confirmation=False,
    )


def _bundle(snapshot_id: str) -> tuple[dict[str, object], dict[str, object]]:
    return {"snapshot_id": snapshot_id}, {"snapshot_id": snapshot_id, "memory_ctx": {}}


def test_a_brief_is_handed_out_once() -> None:
    cache = BriefCache()
    cache.put("c:default", "fp", *_bundle("first"))

    assert cache.take("c:default", "fp") is not None
    assert cache.take("c:default", "fp") is None


def test_a_brief_a_minute_old_is_not_handed_out() -> None:
    """The prewarm bridges the focus to the send; memory the user changed since then must not be hidden by it."""
    cache = BriefCache()
    cache.put("c:default", "fp", *_bundle("first"))
    key = "c:default:fp"
    entry = cache._entries[key]
    cache._entries[key] = dataclasses.replace(entry, stored_at=entry.stored_at - 60.0)

    assert cache.take("c:default", "fp") is None


@pytest.mark.asyncio
async def test_the_next_turn_builds_its_own_brief_instead_of_reusing_the_first() -> None:
    coordinator = TurnPrewarmCoordinator()
    prewarmed_preview, prewarmed_snapshot = _bundle("prewarmed")
    fresh_preview, fresh_snapshot = _bundle("fresh")
    build = AsyncMock(return_value=(fresh_preview, fresh_snapshot))
    coordinator._brief_cache.put(f"{_CHAT_ID}:{_AGENT_ID}", "fp", prewarmed_preview, prewarmed_snapshot)

    with (
        patch(f"{_COORDINATOR}.AgentFactory.create_general_agent"),
        patch(f"{_COORDINATOR}.compute_execution_fingerprint", return_value="fp"),
        patch(f"{_COORDINATOR}.build_execution_scope_key", return_value=f"{_CHAT_ID}:{_AGENT_ID}"),
        patch.object(coordinator, "_should_warm_agent", return_value=False),
        patch("app.services.agent.stream_session.memory_brief.build_memory_brief_snapshot", new=build),
    ):
        first = await coordinator.join_for_turn(MagicMock(chat_id=_CHAT_ID, agent_id=_AGENT_ID, enable_memory=True))
        second = await coordinator.join_for_turn(
            MagicMock(chat_id=_CHAT_ID, agent_id=_AGENT_ID, enable_memory=True), join_timeout=_JOIN_BUDGET_SECONDS
        )

    assert first.snapshot == prewarmed_snapshot
    assert second.snapshot == fresh_snapshot
    assert second.brief_status == {"state": "ready", "source": "preflight"}
    build.assert_awaited_once()


@pytest.fixture
async def stored_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MemoryManager]:
    """A real memory manager on an isolated store; the brief builder reads the same store through its own manager."""
    await clear_embedded_stores()
    monkeypatch.setattr(QdrantVectorStore, "RETRY_BASE_DELAY", 0.0)
    monkeypatch.setattr(
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
        AsyncMock(return_value=None),
    )
    real_create = memory_setup.create_memory_manager

    async def isolated_create(binding, embedding_config, **kwargs):  # noqa: ANN001, ANN003, ANN202
        return await real_create(binding, embedding_config, base_path=tmp_path / "memory", **kwargs)

    monkeypatch.setattr("app.services.agent.stream_session.memory_brief.create_memory_manager", isolated_create)
    binding = memory_setup.resolve_context_binding(
        namespaces=None,
        agent_id=_AGENT_ID,
        channel_id=None,
        conversation_id=_CHAT_ID,
        task_id=None,
        shared_context_ids=[],
        memory_policy=None,
    )
    manager = await isolated_create(binding, None, approval_required=False)
    try:
        yield manager
    finally:
        await manager.close()
        memory_setup._memory_manager_cache.clear()
        await clear_embedded_stores()


def _rule_actions(snapshot: dict[str, object] | None) -> list[str]:
    assert snapshot is not None
    memory_ctx = snapshot["memory_ctx"]
    assert isinstance(memory_ctx, dict)
    rules = memory_ctx["rules"]
    assert isinstance(rules, list)
    return [str(rule["action"]) for rule in rules]


@pytest.mark.asyncio
async def test_a_rule_changed_between_turns_reaches_the_next_turn(stored_memory: MemoryManager) -> None:
    coordinator = TurnPrewarmCoordinator()
    params = _params()
    await stored_memory.add_rule("always", "end every reply with the line - Quill")

    with (
        patch(f"{_COORDINATOR}.AgentFactory.create_general_agent"),
        patch(f"{_COORDINATOR}.compute_execution_fingerprint", return_value="fp"),
        patch.object(coordinator, "_should_warm_agent", return_value=False),
    ):
        first = await coordinator.join_for_turn(params, join_timeout=_JOIN_BUDGET_SECONDS)
        await stored_memory.add_rule("always", "end every reply with the line - Pip")
        second = await coordinator.join_for_turn(params, join_timeout=_JOIN_BUDGET_SECONDS)
        third = await coordinator.join_for_turn(params, join_timeout=_JOIN_BUDGET_SECONDS)

    assert _rule_actions(first.snapshot) == ["end every reply with the line - Quill"]
    assert _rule_actions(second.snapshot) == [
        "end every reply with the line - Pip",
        "end every reply with the line - Quill",
    ]
    # Rebuilding every turn costs nothing at the provider: an unedited memory gives the same block, so the prompt prefix
    # stays cached.
    assert third.snapshot == second.snapshot
