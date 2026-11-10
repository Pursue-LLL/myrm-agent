"""What ``MemoryPreCompactService`` declines to recall, how it builds its query and how it fits its budget."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import cast

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from myrm_agent_harness.agent.context_management.archive_checkpoint import store as archive_store
from myrm_agent_harness.agent.context_management.archive_checkpoint.types import ArchiveCheckpointRecord
from myrm_agent_harness.agent.context_management.infra.schemas import PreCompactInjection
from myrm_agent_harness.agent.context_management.pre_compact_service import (
    MemoryPreCompactConfig,
    MemoryPreCompactService,
)
from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory

pytestmark = pytest.mark.asyncio


class _Manager:
    """Stands in for ``MemoryManager``: ``search`` answers with ``results``, fails, or stalls."""

    def __init__(
        self, results: list[MemorySearchResult] | None = None, *, error: Exception | None = None, delay: float = 0.0
    ) -> None:
        self.results = results or []
        self.error = error
        self.delay = delay
        self.queries: list[str] = []

    async def search(self, query: str, *, limit: int = 10, use_rrf: bool = True) -> list[MemorySearchResult]:
        self.queries.append(query)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.results


def _memory(memory_id: str, content: str = "A durable fact.") -> MemorySearchResult:
    memory = SemanticMemory(id=memory_id, content=content, created_at=datetime.now(UTC))
    return MemorySearchResult(memory=memory, score=0.5, memory_type=MemoryType.SEMANTIC)


def _checkpoint(
    memory_id: str, *, summary: str = "Q3 revenue fell 12%.", path: str = ".ctx/out.txt"
) -> ArchiveCheckpointRecord:
    return ArchiveCheckpointRecord(
        memory_id=memory_id, tool_name="grep_tool", archive_path=path, summary=summary, chat_id="chat-1"
    )


def _archive_returns(monkeypatch: pytest.MonkeyPatch, outcome: list[ArchiveCheckpointRecord] | Exception) -> list[str]:
    """Make the archive scroll answer with ``outcome``; the returned list collects the chats it was asked about."""
    scrolled: list[str] = []

    async def scroll(manager: MemoryManager, *, chat_id: str, limit: int = 8) -> list[ArchiveCheckpointRecord]:
        scrolled.append(chat_id)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(archive_store, "list_recent_checkpoints", scroll)
    return scrolled


async def _recall(
    manager: _Manager,
    messages: list[BaseMessage] | None = None,
    *,
    chat_id: str | None = None,
    hint: str = "",
    config: MemoryPreCompactConfig | None = None,
) -> PreCompactInjection | None:
    service = MemoryPreCompactService(cast("MemoryManager", manager), config)
    return await service.build_injection(
        messages=messages if messages is not None else [HumanMessage(content="continue the refactor")],
        chat_id=chat_id,
        user_id="user-1",
        compaction_tier="compress",
        token_pressure_ratio=0.5,
        user_goal_hint=hint,
    )


class TestWhatIsNotRecalled:
    async def test_a_disabled_service_does_not_even_search(self) -> None:
        manager = _Manager([_memory("mem-12345678")])

        assert await _recall(manager, config=MemoryPreCompactConfig(enabled=False)) is None
        assert manager.queries == []

    async def test_with_nothing_to_ask_about_nothing_is_searched(self) -> None:
        manager = _Manager([_memory("mem-12345678")])

        assert await _recall(manager, [runtime_human_message("notice"), AIMessage(content="")]) is None
        assert manager.queries == []

    async def test_a_search_that_times_out_recalls_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        manager = _Manager([_memory("mem-12345678")], delay=1.0)

        with caplog.at_level(logging.WARNING):
            assert await _recall(manager, config=MemoryPreCompactConfig(timeout_seconds=0.01)) is None

        assert "timed out" in caplog.text

    async def test_a_search_that_fails_recalls_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            assert await _recall(_Manager(error=RuntimeError("index offline"))) is None

        assert "index offline" in caplog.text

    async def test_no_memory_and_no_archive_recalls_nothing(self) -> None:
        assert await _recall(_Manager([])) is None

    async def test_a_memory_already_quoted_in_the_conversation_is_not_recalled_again(self) -> None:
        history: list[BaseMessage] = [
            AIMessage(content=""),
            AIMessage(content="Recalled earlier: id:mem-auth-rule says never touch auth"),
        ]

        assert await _recall(_Manager([_memory("mem-auth-rule")]), history) is None

    async def test_a_memory_too_big_for_the_budget_recalls_nothing(self) -> None:
        # The line's own prefix (it carries the id) already exceeds any budget the service allows.
        assert await _recall(_Manager([_memory("m" * 9000)])) is None


class TestTheBudget:
    async def test_recall_stops_when_the_budget_is_spent(self) -> None:
        memories = [_memory(f"mem-{i:08d}", "x" * 1500) for i in range(8)]

        injection = await _recall(_Manager(memories))

        assert injection is not None
        kept = len(injection.recalled_ids)
        assert 1 <= kept < len(memories)
        assert injection.recalled_ids == tuple(f"mem-{i:08d}" for i in range(kept))

    async def test_archive_recall_stops_when_its_budget_is_spent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        records = [_checkpoint(f"ckpt-{i:08d}", summary="y" * 1500) for i in range(4)]
        _archive_returns(monkeypatch, records)

        injection = await _recall(_Manager([]), chat_id="chat-1")

        assert injection is not None
        assert 1 <= len(injection.recalled_ids) < len(records)

    async def test_an_archive_record_too_big_for_its_budget_recalls_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _archive_returns(monkeypatch, [_checkpoint("ckpt-00000001", path="p" * 9000)])

        assert await _recall(_Manager([]), chat_id="chat-1") is None

    async def test_a_generous_configured_budget_is_capped_at_two_thousand_tokens(self) -> None:
        # 2,000 tokens are 8,000 characters: nine lines of the 900-character content cap, not the eleven a higher
        # ceiling would admit.
        memories = [_memory(f"mem-{i:08d}", "x" * 1500) for i in range(15)]
        config = MemoryPreCompactConfig(budget_tokens=50_000, search_limit=15)

        injection = await _recall(_Manager(memories), config=config)

        assert injection is not None
        assert len(injection.recalled_ids) == 9

    async def test_a_tiny_configured_budget_is_raised_to_eight_hundred_tokens(self) -> None:
        # 800 tokens are 3,200 characters: three full lines and a fourth cut down to what is left.
        memories = [_memory(f"mem-{i:08d}", "x" * 1500) for i in range(8)]

        injection = await _recall(_Manager(memories), config=MemoryPreCompactConfig(budget_tokens=100))

        assert injection is not None
        assert len(injection.recalled_ids) == 4

    async def test_archive_recall_takes_at_most_four_checkpoints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _archive_returns(monkeypatch, [_checkpoint(f"ckpt-{i:08d}", summary="short") for i in range(6)])

        injection = await _recall(_Manager([]), chat_id="chat-1")

        assert injection is not None
        assert injection.recalled_ids == tuple(f"ckpt-{i:08d}" for i in range(4))

    async def test_archive_recall_gets_a_third_of_a_generous_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A 2,000-token budget leaves 666 tokens (2,664 characters) for checkpoints: two full 900-character
        # summaries and a third cut to fit, not the fourth a larger share would admit.
        _archive_returns(monkeypatch, [_checkpoint(f"ckpt-{i:08d}", summary="y" * 900) for i in range(6)])

        injection = await _recall(_Manager([]), chat_id="chat-1", config=MemoryPreCompactConfig(budget_tokens=4000))

        assert injection is not None
        assert len(injection.recalled_ids) == 3

    async def test_archive_recall_never_gets_less_than_four_hundred_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The 800-token floor would leave a third of 266 tokens; 400 tokens (1,600 characters) fit one full
        # 900-character summary and a second cut to fit.
        _archive_returns(monkeypatch, [_checkpoint(f"ckpt-{i:08d}", summary="y" * 900) for i in range(6)])

        injection = await _recall(_Manager([]), chat_id="chat-1", config=MemoryPreCompactConfig(budget_tokens=100))

        assert injection is not None
        assert len(injection.recalled_ids) == 2


class TestArchiveCheckpoints:
    async def test_a_failing_archive_scroll_leaves_the_memory_recall_intact(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _archive_returns(monkeypatch, RuntimeError("vector store offline"))

        injection = await _recall(_Manager([_memory("mem-12345678")]), chat_id="chat-1")

        assert injection is not None
        assert injection.recalled_ids == ("mem-12345678",)
        assert "Recent Archive Checkpoints" not in str(injection.message.content)

    async def test_checkpoints_already_quoted_in_the_conversation_are_not_recalled_again(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _archive_returns(monkeypatch, [_checkpoint("ckpt-00000001")])
        history: list[BaseMessage] = [AIMessage(content="See id:ckpt-00000001 for the earlier output")]

        assert await _recall(_Manager([]), history, chat_id="chat-1") is None

    async def test_without_a_chat_the_archive_is_not_consulted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        scrolled = _archive_returns(monkeypatch, [_checkpoint("ckpt-00000001")])

        injection = await _recall(_Manager([_memory("mem-12345678")]), chat_id=None)

        assert injection is not None
        assert injection.recalled_ids == ("mem-12345678",)
        assert scrolled == []

    async def test_checkpoints_lead_the_memories_in_one_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        scrolled = _archive_returns(monkeypatch, [_checkpoint("ckpt-00000001")])

        injection = await _recall(_Manager([_memory("mem-12345678")]), chat_id="chat-1")

        assert injection is not None
        assert scrolled == ["chat-1"]
        assert injection.recalled_ids == ("ckpt-00000001", "mem-12345678")
        content = str(injection.message.content)
        assert content.index("Recent Archive Checkpoints") < content.index("Pre-Compaction Memory Recall")


class TestTheQuery:
    async def test_it_is_the_goal_then_the_five_most_recent_turns_with_long_answers_cut(self) -> None:
        manager = _Manager()
        history: list[BaseMessage] = [HumanMessage(content=f"user turn {i}") for i in range(7)]
        history.append(AIMessage(content="a" * 900))

        await _recall(manager, history, hint="  refactor payment  ")

        assert manager.queries == ["refactor payment\nuser turn 3\nuser turn 4\nuser turn 5\nuser turn 6\n" + "a" * 400]

    async def test_runtime_notices_and_earlier_recall_injections_say_nothing_about_the_topic(self) -> None:
        manager = _Manager()
        history: list[BaseMessage] = [
            HumanMessage(content="rename the module"),
            HumanMessage(content='<pre_compact_recall_context tier="compress">old recall</pre_compact_recall_context>'),
            runtime_human_message("[constraint] no network"),
        ]

        await _recall(manager, history)

        assert manager.queries == ["rename the module"]

    async def test_only_the_text_blocks_of_a_multimodal_message_count(self) -> None:
        manager = _Manager()
        history: list[BaseMessage] = [
            HumanMessage(
                content=[
                    {"type": "text", "text": "first part"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    {"type": "text", "text": "second part"},
                    {"type": "text", "text": 5},
                ]
            ),
            HumanMessage.model_construct(content=5),
        ]

        await _recall(manager, history)

        assert manager.queries == ["first part\nsecond part"]
