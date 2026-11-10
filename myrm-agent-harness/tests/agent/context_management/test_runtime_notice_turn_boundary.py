"""A notice the runtime appended mid-turn never starts a turn for the context-management readers.

Request-local notices (circuit-breaker constraints, citation rules) stay in the history of a run once they are written, so
every reader that treats "the latest HumanMessage" as the start of the turn has to skip them. Each test builds a history
where the old rule picks the notice and asserts the reader picks the user's own message.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.agent._internals.context_budget import resolve_context_budget_breakdown
from myrm_agent_harness.agent.context_management.infra.message_priority import last_iteration_flags
from myrm_agent_harness.agent.context_management.infra.schemas import StructuredSummary
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor import CompressProcessor
from myrm_agent_harness.agent.context_management.pipeline.processors.reasoning_anchor_processor import (
    ReasoningAnchorProcessor,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.session_notes_processor import (
    _anchor_last_user_message,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.fallback import (
    _build_deterministic_summary,
)
from myrm_agent_harness.agent.context_management.pre_compact_service import _build_query
from myrm_agent_harness.agent.context_management.strategies.reasoning.anchor_ledger import clear_session_anchor_ledger
from myrm_agent_harness.agent.context_management.strategies.session_notes.trigger import (
    _has_tool_calls_in_last_assistant_turn,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summary_builder import (
    create_summary_message,
    extract_protected_head,
    extract_recent_messages_with_split_context,
)
from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.runtime import checkpointing

_NOTICE_TEXT = "[constraint] the sandbox has no network"


def _tool_round(call_id: str, output: str = "out") -> list[BaseMessage]:
    return [
        AIMessage(content="", tool_calls=[{"name": "tool", "args": {}, "id": call_id}]),
        ToolMessage(content=output, tool_call_id=call_id),
    ]


def test_the_iteration_in_progress_starts_at_the_users_message() -> None:
    messages = [
        HumanMessage(content="q"),
        *_tool_round("c1"),
        runtime_human_message(_NOTICE_TEXT),
        AIMessage(content="answer"),
    ]

    flags = last_iteration_flags(messages)

    assert [flags[id(m)] for m in messages] == [False, True, True, True, True]


def test_without_a_user_message_nothing_is_in_the_last_iteration() -> None:
    messages = [AIMessage(content="a"), runtime_human_message(_NOTICE_TEXT)]

    assert not any(last_iteration_flags(messages).values())


def test_the_keep_region_is_anchored_on_the_users_message() -> None:
    messages = [
        HumanMessage(content="old"),
        AIMessage(content="a"),
        HumanMessage(content="task"),
        *_tool_round("c1"),
        runtime_human_message(_NOTICE_TEXT),
    ]

    assert _anchor_last_user_message(messages, start=5) == 2
    assert _anchor_last_user_message(messages, start=1) == 1


def test_the_protected_head_skips_a_notice_before_the_first_user_message() -> None:
    messages = [
        SystemMessage(content="sys"),
        runtime_human_message(_NOTICE_TEXT),
        HumanMessage(content="first"),
        AIMessage(content="reply"),
    ]

    assert [m.content for m in extract_protected_head(messages)] == ["sys", "first", "reply"]


def test_a_split_turn_keeps_the_users_message_as_the_goal() -> None:
    big = "x" * 400
    messages = [
        HumanMessage(content="task"),
        *_tool_round("c1", big),
        runtime_human_message(_NOTICE_TEXT),
        *_tool_round("c2", big),
        *_tool_round("c3", big),
    ]

    result = extract_recent_messages_with_split_context(messages, tail_budget_tokens=20)

    assert result.is_split_turn
    assert result.split_human_message is messages[0]


def test_the_deterministic_summary_takes_the_goal_from_the_users_message() -> None:
    messages = [
        HumanMessage(content="build the quarterly report"),
        AIMessage(content="working"),
        runtime_human_message(_NOTICE_TEXT),
    ]

    summary = _build_deterministic_summary(messages, {})

    assert "build the quarterly report" in summary.active_task
    assert _NOTICE_TEXT not in summary.active_task


def test_the_recall_query_ignores_notices() -> None:
    messages = [
        HumanMessage(content="compare the two databases"),
        AIMessage(content="looking"),
        runtime_human_message(_NOTICE_TEXT),
    ]

    query = _build_query(messages, "")

    assert "compare the two databases" in query
    assert _NOTICE_TEXT not in query


def test_a_history_whose_user_message_was_summarized_is_no_split_turn() -> None:
    big = "x" * 400
    summary = create_summary_message(StructuredSummary(user_goal="folded into the summary"))
    messages = [summary, *_tool_round("c1", big), runtime_human_message(_NOTICE_TEXT), *_tool_round("c2", big)]

    result = extract_recent_messages_with_split_context(messages, tail_budget_tokens=20)

    assert not result.is_split_turn
    assert result.split_human_message is None
    assert result.turn_prefix_messages == []


def test_a_notice_behind_the_tool_results_does_not_end_the_assistant_turn_in_flight() -> None:
    in_flight = [HumanMessage(content="task"), *_tool_round("c1"), runtime_human_message(_NOTICE_TEXT)]
    answered = [*in_flight, AIMessage(content="done"), HumanMessage(content="next task")]

    assert _has_tool_calls_in_last_assistant_turn(in_flight)
    assert not _has_tool_calls_in_last_assistant_turn(answered)


class _RecordingBudget:
    """Stands in for the context budget and records the turn count the compress threshold is sized by."""

    def __init__(self) -> None:
        self.turn_counts: list[int] = []

    def calculate_dynamic_thresholds(self, *, turn_count: int, estimated_remaining_turns: int = 10) -> tuple[int, int]:
        self.turn_counts.append(turn_count)
        return 10**9, 0


async def test_the_compress_threshold_is_sized_by_the_messages_the_user_wrote() -> None:
    budget = _RecordingBudget()
    messages = [
        HumanMessage(content="one"),
        AIMessage(content="a"),
        HumanMessage(content="two"),
        runtime_human_message(_NOTICE_TEXT),
    ]
    context = ProcessorContext(messages=messages, user_query="two", user_id="user-1", chat_id="chat-1")
    target = (
        "myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor.calculate_context_budget"
    )

    with patch(target, return_value=budget):
        assert not await CompressProcessor(max_context_tokens=10_000).should_process(context)

    assert budget.turn_counts == [2]


async def test_the_budget_breakdown_counts_the_messages_the_user_wrote(monkeypatch: pytest.MonkeyPatch) -> None:
    async def checkpoint(checkpointer: object | None, thread_id: str) -> list[object]:
        return [
            HumanMessage(content="one"),
            AIMessage(content="a"),
            HumanMessage(content="two"),
            runtime_human_message(_NOTICE_TEXT),
        ]

    monkeypatch.setattr(checkpointing, "read_checkpoint_messages", checkpoint)

    breakdown = await resolve_context_budget_breakdown(
        checkpointer=object(), thread_id="thread-1", cached_tools=None, provider_prompt_tokens=1_000
    )

    assert breakdown["turn_count"] == 2


@pytest.mark.asyncio
async def test_the_anchor_block_lands_on_the_users_message_and_the_turn_count_ignores_notices() -> None:
    session_id = "notice-turn-boundary-session"
    clear_session_anchor_ledger(session_id)
    earlier = AIMessage(
        content="Plan confirmed", additional_kwargs={"reasoning_content": "核心决策: 统一使用 SQLite 存储"}
    )
    user = HumanMessage(content="收到，请执行。", id="u1")
    notice = runtime_human_message(_NOTICE_TEXT)
    ctx = ProcessorContext(messages=[earlier, user, *_tool_round("c1"), notice], user_query="执行", chat_id=session_id)

    result = await ReasoningAnchorProcessor().process(ctx)

    assert "[PRESERVED REASONING ANCHORS & CONSTRAINTS]" in str(result.messages[1].content)
    assert result.messages[-1].content == _NOTICE_TEXT
    clear_session_anchor_ledger(session_id)
