"""Tests for memory brief preflight snapshot builder."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import set_memory_manager
from myrm_agent_harness.toolkits.memory.config import RecallMode
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from myrm_agent_harness.toolkits.vector.qdrant.store import QdrantVectorStore
from pydantic import Field

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
                    "peer_profile": {"tone": "concise", "city": "Hangzhou"},
                    "agent_instructions": [{"instruction": "Always summarize first"}],
                    "rules": [{"trigger": "doc", "action": "cite sources"}],
                    "working_state": "editing the report",
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
        assert set(snapshot) == {"snapshot_id", "memory_ctx"}
        assert preview["snapshot_id"] == snapshot["snapshot_id"]
        assert preview["namespaces"] == ["global", "agent:default"]
        assert preview["stable"]["working_state"] is True
        assert preview["stable"]["profile_count"] == 3
        assert preview["stable"]["instruction_count"] == 1
        assert preview["stable"]["rule_count"] == 1
        assert preview["is_cold_start"] is False
        assert snapshot["memory_ctx"]["global_profile"]["language"] == "zh-CN"
        assert manager.get_context.await_count == 1

    @pytest.mark.asyncio
    async def test_no_brief_when_the_stored_context_cannot_be_read(self) -> None:
        manager = SimpleNamespace(get_context=AsyncMock(side_effect=RuntimeError("store unavailable")))

        with (
            patch(
                "app.services.agent.stream_session.memory_brief.resolve_context_binding",
                return_value=SimpleNamespace(namespaces=("global",)),
            ),
            patch(
                "app.services.agent.stream_session.memory_brief.create_memory_manager",
                return_value=manager,
            ),
        ):
            bundle = await build_memory_brief_snapshot(_make_params())  # type: ignore[arg-type]

        assert bundle is None


class TestKeywordMode:
    """No embedding configured: the brief is built from the same relational context as for any user."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("saves_rule", [True, False], ids=["profile_and_rule", "profile_only"])
    async def test_brief_counts_the_stored_profile_and_rules(
        self, saves_rule: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A profile fact saved in chat is scoped to the agent, not to ``global``: the brief still counts it, and a
        user whose only memory is that fact is not reported as a cold start."""
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
            if saves_rule:
                await manager.add_rule("deploying", "run smoke tests first")

            bundle = await build_memory_brief_snapshot(params)  # type: ignore[arg-type]

            assert bundle is not None
            preview, snapshot = bundle
            expected = await manager.get_context(include_profile=True, include_rules=True, include_agent_instructions=True)
            assert snapshot["memory_ctx"] == expected
            assert snapshot["memory_ctx"]["peer_profile"]["language"] == "zh-CN"
            assert preview["stable"]["profile_count"] == 1
            assert preview["stable"]["rule_count"] == int(saves_rule)
            assert preview["is_cold_start"] is False
            assert embeddings_seen == [None, None]
        finally:
            await manager.close()
            memory_setup._memory_manager_cache.clear()
            await clear_embedded_stores()


_NO_MEMORY: dict[str, object] = {"global_profile": {}, "peer_profile": {}, "rules": [], "agent_instructions": []}

# One context per kind of content the block can render, each differing from the empty one in that kind only.
_CONTENT_BY_KIND: dict[str, dict[str, object]] = {
    "working_state": {**_NO_MEMORY, "working_state": "editing the report"},
    "global_profile": {**_NO_MEMORY, "global_profile": {"language": "zh-CN"}},
    "peer_profile": {**_NO_MEMORY, "peer_profile": {"language": "zh-CN"}},
    "instructions": {**_NO_MEMORY, "agent_instructions": [{"instruction": "Always summarize first", "priority": 1}]},
    "rules": {
        **_NO_MEMORY,
        "rules": [{"trigger": "deploy", "action": "run smoke tests", "priority": 0, "user_endorsed": False}],
    },
}


@tool
def memory_search_tool(query: str) -> str:
    """Search the user's stored memory."""
    return ""


class _RecordingModel(BaseChatModel):
    """Answers "ok" and records the system messages each call was sent."""

    system_texts: list[list[str]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording"

    def bind_tools(self, tools: object, **kwargs: object) -> _RecordingModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.system_texts.append([str(m.content) for m in messages if isinstance(m, SystemMessage)])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


async def _brief_for(memory_ctx: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    manager = SimpleNamespace(get_context=AsyncMock(return_value=dict(memory_ctx)))
    with (
        patch(
            "app.services.agent.stream_session.memory_brief.resolve_context_binding",
            return_value=SimpleNamespace(namespaces=("global",)),
        ),
        patch("app.services.agent.stream_session.memory_brief.create_memory_manager", return_value=manager),
    ):
        bundle = await build_memory_brief_snapshot(_make_params())  # type: ignore[arg-type]
    assert bundle is not None
    return bundle


async def _injected_memory_block(snapshot: dict[str, object]) -> str:
    """The ``<user_memory_context>`` text the real middleware puts into a model call for ``snapshot``.

    The memory search tool is bound, as it is for a real agent, so an empty memory yields the cold-start guidance.
    """
    model = _RecordingModel()
    graph = create_agent(
        model,
        tools=[memory_search_tool],
        middleware=[memory_context_middleware],
        checkpointer=InMemorySaver(),
        system_prompt="<identity>You are the test agent.</identity>",
    )
    config = {"configurable": {"thread_id": uuid4().hex}}
    await graph.ainvoke({"messages": [HumanMessage(content="hello")]}, config, context={"memory_brief_snapshot": snapshot})
    blocks = [text for text in model.system_texts[0] if text.lstrip().startswith("<user_memory_context")]
    assert len(blocks) == 1
    return blocks[0]


class TestColdStartMatchesInjectedBlock:
    """``is_cold_start`` says what the memory block handed to the model says."""

    @pytest.fixture(autouse=True)
    def _bound_memory_manager(self) -> Iterator[None]:
        manager = MagicMock()
        manager.recall_mode = RecallMode.HYBRID
        manager.user_id = "u1"
        set_memory_manager(manager)
        try:
            yield
        finally:
            set_memory_manager(None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["empty", *_CONTENT_BY_KIND])
    async def test_flag_agrees_with_the_block(self, kind: str) -> None:
        preview, snapshot = await _brief_for(_NO_MEMORY if kind == "empty" else _CONTENT_BY_KIND[kind])
        cold_block = await _injected_memory_block((await _brief_for(_NO_MEMORY))[1])
        block = await _injected_memory_block(snapshot)

        assert preview["is_cold_start"] is (kind == "empty")
        assert (block == cold_block) is preview["is_cold_start"]
