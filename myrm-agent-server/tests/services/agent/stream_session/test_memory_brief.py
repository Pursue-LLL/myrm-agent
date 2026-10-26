"""Tests for memory brief preflight snapshot builder."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore

from app.core.memory.adapters import setup as memory_setup
from app.services.agent.stream_session.memory_brief import build_memory_brief_snapshot


def _make_params(**overrides: object) -> SimpleNamespace:
    params = SimpleNamespace(
        enable_memory=True,
        incognito_mode=False,
        embedding_config=object(),
        memory_conversation_id="chat-1",
        chat_id="chat-1",
        declared_allowed_roots=[],
        agent_id="agent-default",
        memory_channel_id=None,
        channel_name=None,
        memory_task_id=None,
        memory_shared_context_ids=[],
        memory_policy=None,
        memory_require_confirmation=False,
    )
    for key, value in overrides.items():
        setattr(params, key, value)
    return params


class TestBuildMemoryBriefSnapshot:
    @pytest.mark.asyncio
    async def test_returns_none_when_memory_disabled(self) -> None:
        params = _make_params(enable_memory=False)
        bundle = await build_memory_brief_snapshot(params)  # type: ignore[arg-type]
        assert bundle is None

    @pytest.mark.asyncio
    async def test_builds_preview_and_snapshot_from_same_payload(self) -> None:
        params = _make_params()
        binding = SimpleNamespace(namespaces=("global", "agent:default"))
        manager = SimpleNamespace(
            get_context=AsyncMock(
                return_value={
                    "global_profile": {"language": "zh-CN"},
                    "agent_instructions": [{"instruction": "Always summarize first"}],
                    "rules": [{"trigger": "doc", "action": "cite sources"}],
                    "working_state": {"phase": "editing"},
                }
            ),
            get_learned_context=AsyncMock(
                return_value={
                    "learned_preferences": [
                        {"id": "pref-1", "content": "prefer concise"},
                        {"id": "pref-2", "content": "avoid emoji", "source_error": "emoji too noisy"},
                    ],
                    "learned_rules": [{"id": "rule-1", "trigger": "risk", "action": "ask confirmation"}],
                }
            ),
        )

        with (
            patch(
                "app.services.agent.stream_session.memory_brief.resolve_context_binding",
                return_value=binding,
            ),
            patch(
                "app.services.agent.stream_session.memory_brief.create_memory_manager",
                return_value=manager,
            ),
        ):
            bundle = await build_memory_brief_snapshot(params)  # type: ignore[arg-type]

        assert bundle is not None
        preview, snapshot = bundle
        assert preview["snapshot_id"] == snapshot["snapshot_id"]
        assert preview["namespaces"] == ["global", "agent:default"]
        assert preview["stable"]["instruction_count"] == 1
        assert preview["stable"]["rule_count"] == 1
        assert preview["learned"]["preference_count"] == 2
        assert preview["learned"]["rule_count"] == 1
        assert preview["learned"]["correction_count"] == 1
        assert preview["learned"]["preference_ids"] == ["pref-1", "pref-2"]
        assert preview["learned"]["rule_ids"] == ["rule-1"]
        assert snapshot["memory_ctx"]["global_profile"]["language"] == "zh-CN"
        assert manager.get_context.await_count == 1
        assert manager.get_learned_context.await_count == 1

    @pytest.mark.asyncio
    async def test_learned_failure_degrades_to_empty_learned_payload(self) -> None:
        params = _make_params()
        binding = SimpleNamespace(namespaces=("global",))
        manager = SimpleNamespace(
            get_context=AsyncMock(return_value={"global_profile": {"name": "Ada"}}),
            get_learned_context=AsyncMock(side_effect=RuntimeError("learned unavailable")),
        )

        with (
            patch(
                "app.services.agent.stream_session.memory_brief.resolve_context_binding",
                return_value=binding,
            ),
            patch(
                "app.services.agent.stream_session.memory_brief.create_memory_manager",
                return_value=manager,
            ),
        ):
            bundle = await build_memory_brief_snapshot(params)  # type: ignore[arg-type]

        assert bundle is not None
        preview, snapshot = bundle
        assert preview["learned"]["preference_count"] == 0
        assert preview["learned"]["rule_count"] == 0
        assert snapshot["learned_ctx"] == {"learned_rules": [], "learned_preferences": []}


class TestKeywordMode:
    """No embedding configured: the brief is built from the same relational context as for any user."""

    @pytest.mark.asyncio
    async def test_brief_carries_the_stored_profile_and_rules(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        await clear_embedded_stores()
        monkeypatch.setattr(QdrantVectorStore, "RETRY_BASE_DELAY", 0.0)
        monkeypatch.setattr(
            "app.services.memory.extract_retry.resolve_chat_extraction_llm.get_platform_dedup_llm",
            AsyncMock(return_value=None),
        )
        real_create = memory_setup.create_memory_manager
        embeddings_seen: list[object] = []

        async def isolated_create(binding, embedding_config, **kwargs):  # noqa: ANN001, ANN003, ANN202
            embeddings_seen.append(embedding_config)
            return await real_create(binding, embedding_config, base_path=tmp_path / "memory", **kwargs)

        monkeypatch.setattr(
            "app.services.agent.stream_session.memory_brief.create_memory_manager",
            isolated_create,
        )
        params = _make_params(embedding_config=None)
        binding = memory_setup.resolve_context_binding(
            namespaces=None,
            agent_id="agent-default",
            channel_id=None,
            conversation_id="chat-1",
            task_id=None,
            shared_context_ids=[],
            memory_policy=None,
        )
        manager = await isolated_create(binding, None, approval_required=False)
        try:
            await manager.set_profile_attribute("language", "zh-CN")
            await manager.add_rule("deploying", "run smoke tests first")

            bundle = await build_memory_brief_snapshot(params)  # type: ignore[arg-type]

            assert bundle is not None
            preview, snapshot = bundle
            expected = await manager.get_context(include_profile=True, include_rules=True, include_agent_instructions=True)
            assert snapshot["memory_ctx"] == expected
            assert snapshot["memory_ctx"]["peer_profile"]["language"] == "zh-CN"
            assert preview["stable"]["rule_count"] == 1
            assert preview["is_cold_start"] is False
            assert embeddings_seen == [None, None]
        finally:
            await manager.close()
            memory_setup._memory_manager_cache.clear()
            await clear_embedded_stores()
