"""Overflow recovery cuts the history at the user's messages, never inside a turn the runtime added notices to."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from myrm_agent_harness.agent._internals.agent_recovery import _TRUNCATION_MARKER, truncate_oldest_rounds
from myrm_agent_harness.core.message_origin import (
    count_user_authored_messages,
    is_user_authored_human_message,
    last_user_authored_index,
    runtime_human_message,
)


def _tool_round(call_id: str) -> list[BaseMessage]:
    call = AIMessage(content="", tool_calls=[{"id": call_id, "name": "search", "args": {}}])
    return [call, ToolMessage(content="result " * 100, tool_call_id=call_id)]


def test_notices_inside_one_turn_do_not_make_it_truncatable() -> None:
    messages: list[BaseMessage] = [
        SystemMessage(content="sys"),
        HumanMessage(content="the request"),
        *_tool_round("c1"),
        runtime_human_message("[notice] one"),
        *_tool_round("c2"),
        runtime_human_message("[notice] two"),
        *_tool_round("c3"),
    ]
    before = list(messages)

    assert truncate_oldest_rounds(messages) == 0

    assert len(messages) == len(before)
    assert all(kept is original for kept, original in zip(messages, before, strict=True))


def test_the_oldest_turn_goes_whole_and_the_notices_stay_with_their_turn() -> None:
    old: list[BaseMessage] = [
        HumanMessage(content="old request"),
        *_tool_round("c1"),
        runtime_human_message("[notice] old"),
    ]
    new: list[BaseMessage] = [
        HumanMessage(content="new request"),
        *_tool_round("c2"),
        runtime_human_message("[notice] new"),
    ]
    system = SystemMessage(content="sys")
    messages: list[BaseMessage] = [system, *old, *new]

    assert truncate_oldest_rounds(messages) > 0

    assert messages[0] is system
    assert messages[1].content == _TRUNCATION_MARKER
    assert len(messages) == 2 + len(new)
    assert all(kept is original for kept, original in zip(messages[2:], new, strict=True))


def test_the_truncation_marker_is_the_runtimes_not_a_turn_of_the_user() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="old request"),
        AIMessage(content="old answer"),
        HumanMessage(content="new request"),
        AIMessage(content="new answer"),
    ]

    truncate_oldest_rounds(messages)

    assert messages[0].content == _TRUNCATION_MARKER
    assert not is_user_authored_human_message(messages[0])
    assert count_user_authored_messages(messages) == 1
    assert messages[last_user_authored_index(messages)].content == "new request"
