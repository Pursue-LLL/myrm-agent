"""The advisor fan-out reads requests that carry notices the runtime appended behind the user's message."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.toolkits.llms.consensus.advisor_fanout import AdvisorFanoutRunner, should_run_fanout
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAOverlayConfig

_CALL = AIMessage(content="", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
_RESULT = ToolMessage(content="found", tool_call_id="c1")


def _opens_a_turn(messages: list[BaseMessage]) -> bool:
    return should_run_fanout(messages=messages, fanout="user_turn", every_n=2, iteration=1)


def test_notices_behind_the_users_message_leave_the_call_a_fresh_turn() -> None:
    user = HumanMessage(content="question")

    assert _opens_a_turn([user, runtime_human_message("[restore] files")]) is True
    assert _opens_a_turn([user, runtime_human_message("[restore] files"), runtime_human_message("[hint]")]) is True


@pytest.mark.parametrize(
    "after_the_user_message",
    [
        [_CALL, _RESULT, runtime_human_message("[notice]")],
        [AIMessage(content="working on it"), runtime_human_message("[notice]")],
        [runtime_human_message("[notice]"), _CALL, _RESULT],
    ],
    ids=["behind-the-tool-results", "behind-an-assistant-message", "notice-then-tool-round"],
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
