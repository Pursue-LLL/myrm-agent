"""The advisor fan-out reads requests that carry notices the runtime appended behind the user's message."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.core.message_origin import runtime_human_message, runtime_system_message
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import (
    AdvisorFanoutRunner,
    _is_runtime_appendix,
    should_run_fanout,
)
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig

_CALL = AIMessage(content="", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
_RESULT = ToolMessage(content="found", tool_call_id="c1")


def _opens_a_turn(messages: list[BaseMessage]) -> bool:
    return should_run_fanout(messages=messages, fanout="user_turn", every_n=2, iteration=1)


def test_notices_behind_the_users_message_leave_the_call_a_fresh_turn() -> None:
    user = HumanMessage(content="question")

    assert _opens_a_turn([user, runtime_human_message("[restore] files")]) is True
    assert _opens_a_turn([user, runtime_human_message("[restore] files"), runtime_human_message("[hint]")]) is True


def test_blocks_the_runtime_added_behind_the_users_message_leave_the_call_a_fresh_turn() -> None:
    # The first call of a chat carries the data-boundary rules, the canary and the session directories as system
    # messages behind the user's own.
    user = HumanMessage(content="question")
    blocks: list[BaseMessage] = [
        SystemMessage(content="<data_boundary_rules>"),
        SystemMessage(content="<session-access>"),
    ]

    assert _opens_a_turn([user, *blocks]) is True
    assert _opens_a_turn([user, *blocks, runtime_human_message("[restore] files")]) is True


@pytest.mark.parametrize(
    "after_the_user_message",
    [
        [_CALL, _RESULT, runtime_human_message("[notice]")],
        [AIMessage(content="working on it"), runtime_human_message("[notice]")],
        [runtime_human_message("[notice]"), _CALL, _RESULT],
        [SystemMessage(content="<session-access>"), _CALL, _RESULT],
        [SystemMessage(content="<session-access>"), AIMessage(content="working on it")],
    ],
    ids=[
        "behind-the-tool-results",
        "behind-an-assistant-message",
        "notice-then-tool-round",
        "block-then-tool-round",
        "block-then-assistant-message",
    ],
)
def test_a_notice_behind_the_assistant_does_not_open_a_turn(after_the_user_message: list[BaseMessage]) -> None:
    assert _opens_a_turn([HumanMessage(content="question"), *after_the_user_message]) is False


def test_the_users_latest_message_opens_the_turn_whatever_came_before_it() -> None:
    history: list[BaseMessage] = [
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
    ]

    assert _opens_a_turn(history) is True


@pytest.mark.parametrize(
    "messages",
    [[], [runtime_human_message("[notice]")]],
    ids=["no-messages", "notice-without-a-user-message"],
)
def test_a_request_without_a_user_message_opens_no_turn(messages: list[BaseMessage]) -> None:
    assert _opens_a_turn(messages) is False


@pytest.mark.asyncio
async def test_the_advisors_are_asked_what_the_user_wrote_not_the_notice_behind_it() -> None:
    runner = AdvisorFanoutRunner([MagicMock(model_name="ref-a")], MoAOverlayConfig(fanout="per_iteration"))
    messages: list[BaseMessage] = [
        HumanMessage(content="what changed in the release?"),
        _CALL,
        _RESULT,
        runtime_human_message("[SYSTEM INSTRUCTION] cite every source"),
    ]

    with patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[]) as asked:
        await runner.run(messages)

    asked.assert_awaited_once()
    assert asked.await_args is not None
    assert asked.await_args.args[0] == "what changed in the release?"


@pytest.mark.asyncio
async def test_the_advisors_are_not_asked_when_only_notices_follow_a_blank_user_message() -> None:
    runner = AdvisorFanoutRunner([MagicMock(model_name="ref-a")], MoAOverlayConfig(fanout="per_iteration"))
    messages: list[BaseMessage] = [HumanMessage(content="   "), runtime_human_message("[notice] not a question")]

    with patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock) as asked:
        assert await runner.run(messages) == []

    asked.assert_not_called()


async def _history_the_advisors_read(
    messages: list[BaseMessage], fanout: str = "user_turn", *, force_run: bool = False
) -> list[BaseMessage] | None:
    runner = AdvisorFanoutRunner([MagicMock(model_name="ref-a")], MoAOverlayConfig(fanout=fanout))
    with patch.object(AdvisorFanoutRunner, "_query_references", new_callable=AsyncMock, return_value=[]) as asked:
        await runner.run(messages, force_run=force_run)

    asked.assert_awaited_once()
    assert asked.await_args is not None
    history: list[BaseMessage] | None = asked.await_args.args[1]
    return history


@pytest.mark.asyncio
async def test_the_advisors_read_the_conversation_before_the_users_message_not_what_follows_it() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="first"),
        AIMessage(content="answer"),
        HumanMessage(content="second"),
        runtime_human_message("[restore] files"),
        runtime_human_message("[SYSTEM INSTRUCTION] cite every source"),
    ]

    history = await _history_the_advisors_read(messages)

    assert history is not None
    assert [message.content for message in history] == ["first", "answer"]


@pytest.mark.asyncio
async def test_the_first_call_of_a_chat_shows_the_advisors_none_of_the_blocks_the_runtime_added() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="question"),
        runtime_system_message("<data_boundary_rules>"),
        runtime_system_message("SECURITY CANARY: token"),
        runtime_system_message("<session-access>"),
    ]

    assert not await _history_the_advisors_read(messages)


@pytest.mark.asyncio
async def test_the_advisors_are_never_shown_the_system_blocks_the_runtime_wrote_for_the_acting_model() -> None:
    memory = SystemMessage(content="<memory-context>", additional_kwargs={"memory_context": True})
    messages: list[BaseMessage] = [
        HumanMessage(content="first"),
        runtime_system_message("<data_boundary_rules>"),
        runtime_system_message("SECURITY CANARY: token"),
        memory,
        AIMessage(content="answer"),
        HumanMessage(content="second"),
    ]

    history = await _history_the_advisors_read(messages)

    assert history is not None
    assert [message.content for message in history] == ["first", "<memory-context>", "answer"]


@pytest.mark.asyncio
async def test_a_step_of_the_tool_loop_does_not_show_the_advisors_the_runtime_blocks_either() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="question"),
        runtime_system_message("SECURITY CANARY: token"),
        _CALL,
        _RESULT,
    ]

    history = await _history_the_advisors_read(messages, fanout="per_iteration")

    assert history is not None
    assert [message.content for message in history] == ["question", "[tool result]: found"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "behind_the_result",
    [
        [],
        [runtime_human_message("[notice]")],
        [runtime_system_message("<session-access>")],
        [
            runtime_human_message("[notice]"),
            runtime_system_message("<session-access>"),
            runtime_human_message("[hint]"),
        ],
    ],
    ids=["nothing", "a-notice", "a-system-block", "several-appendices"],
)
async def test_a_step_of_the_tool_loop_shows_the_advisors_the_work_so_far_up_to_the_latest_result(
    behind_the_result: list[BaseMessage],
) -> None:
    messages: list[BaseMessage] = [HumanMessage(content="question"), _CALL, _RESULT, *behind_the_result]

    history = await _history_the_advisors_read(messages, fanout="per_iteration")

    assert history is not None
    assert [message.content for message in history] == ["question", "[tool result]: found"]


@pytest.mark.asyncio
async def test_the_advisors_a_risk_trigger_summons_read_the_failure_that_triggered_it() -> None:
    failure = ToolMessage(content="Error: 429 rate limited", tool_call_id="c1", name="search", status="error")
    messages: list[BaseMessage] = [HumanMessage(content="find the release notes"), _CALL, failure]

    history = await _history_the_advisors_read(messages, fanout="risk_triggered", force_run=True)

    assert history is not None
    assert [message.content for message in history] == [
        "find the release notes",
        "[search result]: Error: 429 rate limited",
    ]


@pytest.mark.parametrize(
    ("message", "appended_by_the_runtime"),
    [
        (runtime_human_message("[notice]"), True),
        (runtime_system_message("<session-access>"), True),
        (HumanMessage(content="question"), False),
        (SystemMessage(content="<memory-context>", additional_kwargs={"memory_context": True}), False),
        (AIMessage(content="answer"), False),
        (_RESULT, False),
    ],
    ids=["notice", "system-block", "the-users-message", "memory-context", "assistant-message", "tool-result"],
)
def test_only_what_the_runtime_appended_for_the_acting_model_is_an_appendix(
    message: BaseMessage, appended_by_the_runtime: bool
) -> None:
    assert _is_runtime_appendix(message) is appended_by_the_runtime
