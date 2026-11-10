"""Signed reasoning in an Anthropic request: handed back exactly as received, and judged only for the tool loop in progress.

The provider takes a block back only as the leading content of the assistant turn it came with, and refuses a request
whose current tool loop calls tools without one while thinking is on. These tests pin what the request builder sends.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store
from myrm_agent_harness.toolkits.llms.transport import anthropic_messages, openai_chat
from myrm_agent_harness.toolkits.llms.transport.anthropic_thinking import request_thinking
from myrm_agent_harness.toolkits.llms.transport.capabilities import ClaudeTraits
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]

# A dated id the catalog does not list, so the rules come from the model name alone.
MODEL = "claude-sonnet-4-5-20991231"
_THINKING: Message = {"type": "thinking", "thinking": "plan", "signature": "sig-1"}
_REDACTED: Message = {"type": "redacted_thinking", "data": "opaque"}
# What a high-effort request asks of a legacy model that is allowed to think.
_THINKING_ON: Message = {"type": "enabled", "budget_tokens": 4096}
_TEXT: Message = {"type": "text", "text": "plain"}
_TOOL_USE: Message = {"type": "tool_use", "id": "c1", "name": "search", "input": {}}
_TOOL_RESULT: Message = {"type": "tool_result", "tool_use_id": "c1", "content": "result"}


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _body(messages: list[Message]) -> dict[str, object]:
    route = resolve_route(f"anthropic/{MODEL}", api_key="k")
    body = anthropic_messages.prepare(route, messages, {"reasoning_effort": "high", "max_tokens": 9000}).body
    assert body is not None
    return dict(body)


def _call(call_id: str) -> Message:
    return {"id": call_id, "type": "function", "function": {"name": "search", "arguments": json.dumps({"q": call_id})}}


def _round(call_id: str, *blocks: Message, text: str = "") -> list[Message]:
    """One tool round: the assistant turn that calls a tool (with its reasoning blocks) and the tool's result."""
    assistant: Message = {"role": "assistant", "content": text, "tool_calls": [_call(call_id)]}
    if blocks:
        assistant["thinking_blocks"] = list(blocks)
    return [assistant, {"role": "tool", "tool_call_id": call_id, "content": f"result {call_id}"}]


def _assistant_content(body: dict[str, object], turn: int) -> list[Message]:
    turns = body["messages"]
    assert isinstance(turns, list)
    content = turns[turn]["content"]
    assert isinstance(content, list)
    return content


class TestReplayedBlocks:
    def test_blocks_lead_their_turn_in_the_order_received_ahead_of_text_and_tool_calls(self) -> None:
        messages: list[Message] = [
            {"role": "user", "content": "go"},
            *_round("c1", _THINKING, _REDACTED, text="checking"),
        ]

        content = _assistant_content(_body(messages), 1)

        assert [block["type"] for block in content] == ["thinking", "redacted_thinking", "text", "tool_use"]
        assert content[:2] == [_THINKING, _REDACTED]

    def test_a_block_is_sent_exactly_as_received_and_the_conversation_keeps_its_own_copy(self) -> None:
        messages: list[Message] = [{"role": "user", "content": "go"}, *_round("c1", _THINKING)]

        sent = _assistant_content(_body(messages), 1)[0]

        assert sent == _THINKING
        assert sent is not _THINKING
        assert messages[1]["thinking_blocks"] == [_THINKING]

    def test_a_signed_block_without_text_is_replayed(self) -> None:
        omitted: Message = {"type": "thinking", "thinking": "", "signature": "sig-omitted"}

        content = _assistant_content(_body([{"role": "user", "content": "go"}, *_round("c1", omitted)]), 1)

        assert content[0] == omitted

    @pytest.mark.parametrize(
        "unusable",
        [
            {"type": "thinking", "thinking": "plan"},
            {"type": "thinking", "thinking": "plan", "signature": ""},
            {"type": "redacted_thinking", "data": ""},
            {"type": "text", "text": "not reasoning"},
        ],
        ids=["unsigned", "empty-signature", "empty-redacted", "not-a-reasoning-block"],
    )
    def test_a_block_the_provider_would_refuse_is_not_sent(self, unusable: Message) -> None:
        body = _body([{"role": "user", "content": "go"}, *_round("c1", unusable)])

        assert [block["type"] for block in _assistant_content(body, 1)] == ["tool_use"]
        assert "thinking" not in body


class TestThinkingAcrossAToolLoop:
    def test_every_turn_of_the_loop_carrying_its_block_keeps_thinking_on(self) -> None:
        messages: list[Message] = [
            {"role": "user", "content": "go"},
            *_round("c1", _THINKING),
            *_round("c2", _THINKING),
        ]

        assert _body(messages)["thinking"] == _THINKING_ON

    def test_a_redacted_block_leads_a_turn_as_well_as_a_signed_one(self) -> None:
        assert "thinking" in _body([{"role": "user", "content": "go"}, *_round("c1", _REDACTED)])

    def test_one_turn_of_the_loop_without_its_block_switches_thinking_off_for_the_request(self) -> None:
        messages: list[Message] = [{"role": "user", "content": "go"}, *_round("c1", _THINKING), *_round("c2")]

        assert "thinking" not in _body(messages)

    def test_turns_before_the_latest_user_message_are_not_judged(self) -> None:
        earlier: list[Message] = [
            {"role": "user", "content": "first"},
            *_round("c1"),
            {"role": "assistant", "content": "done"},
        ]
        messages: list[Message] = [*earlier, {"role": "user", "content": "second"}, *_round("c2", _THINKING)]

        assert "thinking" in _body(messages)

    def test_a_new_user_message_after_a_loop_without_blocks_has_thinking_back(self) -> None:
        messages: list[Message] = [
            {"role": "user", "content": "first"},
            *_round("c1"),
            {"role": "assistant", "content": "done"},
            {"role": "user", "content": "second"},
        ]

        assert "thinking" in _body(messages)

    def test_a_tool_result_is_not_a_new_user_message(self) -> None:
        # Tool results travel as user turns on this wire; only the user's own message ends the loop.
        messages: list[Message] = [{"role": "user", "content": "go"}, *_round("c1"), *_round("c2", _THINKING)]

        assert "thinking" not in _body(messages)


def _wire_turn(role: str, *blocks: Message) -> Message:
    return {"role": role, "content": list(blocks)}


def _thinking_for(turns: list[Message]) -> object:
    """The ``thinking`` block a high-effort request carries for these wire turns (legacy model: a token budget)."""
    return request_thinking({"reasoning_effort": "high"}, ClaudeTraits(), turns).block


class TestJudgingTheTurnsOnTheWire:
    def test_a_history_without_a_user_message_of_its_own_is_judged_whole(self) -> None:
        turns: list[Message] = [_wire_turn("assistant", _TOOL_USE), _wire_turn("user", _TOOL_RESULT)]

        assert _thinking_for(turns) is None

    def test_a_turn_of_the_loop_that_calls_no_tool_needs_no_block(self) -> None:
        turns: list[Message] = [_wire_turn("user", _TEXT), _wire_turn("assistant", _TEXT)]

        assert _thinking_for(turns) == _THINKING_ON

    def test_the_block_must_lead_the_turn_not_merely_be_in_it(self) -> None:
        lagging: list[Message] = [
            _wire_turn("user", _TEXT),
            _wire_turn("assistant", _TEXT, _THINKING, _TOOL_USE),
            _wire_turn("user", _TOOL_RESULT),
        ]
        leading: list[Message] = [lagging[0], _wire_turn("assistant", _THINKING, _TEXT, _TOOL_USE), lagging[2]]

        assert _thinking_for(lagging) is None
        assert _thinking_for(leading) == _THINKING_ON


class TestOtherWires:
    def test_an_openai_shaped_request_leaves_the_blocks_out(self) -> None:
        route = resolve_route("openai/gpt-4o", api_key="k")
        messages: list[Message] = [{"role": "user", "content": "go"}, *_round("c1", _THINKING)]

        body = openai_chat.prepare(route, messages, {}).body
        assert body is not None
        turns = body["messages"]

        assert isinstance(turns, list)
        assert all("thinking_blocks" not in turn for turn in turns)
        assert messages[1]["thinking_blocks"] == [_THINKING]
