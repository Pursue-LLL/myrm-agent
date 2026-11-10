"""Signed reasoning in a Converse request: judged only for the tool loop in progress, like the Anthropic wire.

Converse carries a tool result as a user turn of ``toolResult`` blocks and puts an assistant "Please continue." between
those results and a user note that follows, so the loop is read from the converted turns, not from the chat history.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store
from myrm_agent_harness.toolkits.llms.transport import bedrock_converse
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]

# A dated id the catalog does not list, so the rules come from the model name alone.
MODEL = "us.anthropic.claude-sonnet-4-5-20991231-v1:0"
_THINKING = {"type": "thinking", "thinking": "plan", "signature": "sig-1"}
_BUDGET = {"thinking": {"type": "enabled", "budget_tokens": 4096}}
_AWS_ENV = ("AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_BEARER_TOKEN_BEDROCK")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _AWS_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(store, "_REGISTERED", {})


def _thinks(messages: list[Message]) -> bool:
    route = resolve_route(f"bedrock/{MODEL}", api_key="k")
    body = bedrock_converse.prepare(route, messages, {"reasoning_effort": "high"}).body
    assert body is not None
    fields = body.get("additionalModelRequestFields", {})
    assert isinstance(fields, dict)
    if "thinking" not in fields:
        return False
    assert fields == _BUDGET
    return True


def _round(call_id: str, *blocks: Message) -> list[Message]:
    call = {"id": call_id, "type": "function", "function": {"name": "search", "arguments": "{}"}}
    assistant: Message = {"role": "assistant", "content": "", "tool_calls": [call]}
    if blocks:
        assistant["thinking_blocks"] = list(blocks)
    return [assistant, {"role": "tool", "tool_call_id": call_id, "content": f"result {call_id}"}]


def _user(text: str) -> Message:
    return {"role": "user", "content": text}


class TestThinkingAcrossAToolLoop:
    def test_every_turn_of_the_loop_carrying_its_block_keeps_thinking_on(self) -> None:
        assert _thinks([_user("go"), *_round("c1", _THINKING), *_round("c2", _THINKING)])

    def test_one_turn_of_the_loop_without_its_block_switches_thinking_off(self) -> None:
        assert not _thinks([_user("go"), *_round("c1", _THINKING), *_round("c2")])

    def test_turns_before_the_latest_user_message_are_not_judged(self) -> None:
        earlier = [_user("first"), *_round("c1"), {"role": "assistant", "content": "done"}]

        assert _thinks([*earlier, _user("second"), *_round("c2", _THINKING)])

    def test_a_user_note_after_the_tool_results_starts_a_new_view_of_the_loop(self) -> None:
        # Converse separates the results from the note with an assistant turn, so the note is the latest user turn.
        assert _thinks([_user("go"), *_round("c1"), _user("note")])
