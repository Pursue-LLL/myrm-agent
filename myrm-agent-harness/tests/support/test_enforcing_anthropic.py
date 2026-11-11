"""The Anthropic double of the replay tests refuses what the API refuses and answers every request shape.

A replay test is only as strict as its provider, so these tests pin the double itself: a green replay test means the
client sent what a provider that checks would take.
"""

from __future__ import annotations

import httpx

from tests.support.enforcing_anthropic import EnforcingAnthropic, RequestRecord

type Json = dict[str, object]

_THINKING: Json = {"type": "enabled", "budget_tokens": 1024}
_TOOLS: list[Json] = [{"name": "read_file", "description": "read a file", "input_schema": {"type": "object"}}]
_USER: Json = {"role": "user", "content": "go"}
_SYSTEM = "rules"


def _request(**body: object) -> httpx.Request:
    payload: Json = {"model": "claude-sonnet-5-5", "max_tokens": 64, "messages": [_USER], **body}
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages", json=payload)


def _first_answer(double: EnforcingAnthropic) -> list[Json]:
    """The blocks of the double's answer to the opening request of a tool loop: reasoning, then a tool call."""
    response = double.handle(_request(thinking=_THINKING, tools=_TOOLS, system=_SYSTEM))
    content: object = response.json()["content"]
    assert isinstance(content, list)
    assert [block["type"] for block in content] == ["thinking", "tool_use"]
    return content


def _follow_up(answer: list[Json], *, system: str = _SYSTEM, keep_reasoning: bool = True) -> httpx.Request:
    """The request that sends the tool's result back, replaying the answer as the client chooses."""
    call = answer[-1]
    result: Json = {"type": "tool_result", "tool_use_id": call["id"], "content": "ok"}
    turns: list[Json] = [
        _USER,
        {"role": "assistant", "content": answer if keep_reasoning else [call]},
        {"role": "user", "content": [result]},
    ]
    return _request(thinking=_THINKING, tools=_TOOLS, system=system, messages=turns)


def test_a_request_that_declares_no_tools_is_answered_with_text() -> None:
    response = EnforcingAnthropic(tool_rounds=2).handle(_request(thinking=_THINKING))

    assert response.status_code == 200
    assert [block["type"] for block in response.json()["content"]] == ["thinking", "text"]


def test_a_block_is_accepted_under_the_prompt_it_was_signed_for_and_refused_under_an_edited_one() -> None:
    double = EnforcingAnthropic(tool_rounds=1)
    answer = _first_answer(double)

    assert double.handle(_follow_up(answer)).status_code == 200
    refused = double.handle(_follow_up(answer, system="rules, edited"))

    assert refused.status_code == 400
    assert "Invalid `signature`" in refused.json()["error"]["message"]
    assert [record.reason for record in double.refused] == ["the prompt before the block changed"]


def test_the_tool_turn_awaiting_its_result_must_lead_with_a_block_while_thinking_is_on() -> None:
    double = EnforcingAnthropic(tool_rounds=1)
    answer = _first_answer(double)

    refused = double.handle(_follow_up(answer, keep_reasoning=False))

    assert refused.status_code == 400
    assert "Expected `thinking` or `redacted_thinking`" in refused.json()["error"]["message"]
    assert [record.reason for record in double.refused] == ["the tool turn awaiting its result lacks a block"]


def test_a_record_holds_the_text_the_model_read_and_none_of_the_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=1)
    answer = _first_answer(double)

    assert double.handle(_follow_up(answer)).status_code == 200

    assert [record.text for record in double.accepted] == ["go", "go\nok"]


def test_the_closing_answer_is_the_text_the_double_was_given() -> None:
    response = EnforcingAnthropic(tool_rounds=0, answer="closing words").handle(_request())

    assert [block["text"] for block in response.json()["content"]] == ["closing words"]


def test_a_turn_opens_with_the_one_request_that_replays_no_block() -> None:
    double = EnforcingAnthropic(tool_rounds=1)
    double.requests += [RequestRecord(200, True, replayed) for replayed in (0, 1, 2, 0, 1, 0)]
    double.requests.append(RequestRecord(400, True, 3, "the run of blocks has a gap"))

    assert [[record.replayed for record in turn] for turn in double.turns] == [[0, 1, 2], [0, 1], [0]]
