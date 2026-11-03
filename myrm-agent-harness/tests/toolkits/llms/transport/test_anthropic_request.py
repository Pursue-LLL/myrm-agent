"""Anthropic Messages request rules that depend on the model or on what the API refuses.

The golden request test pins what the previous client library sent; these tests pin the rules behind the cases it
cannot see: model generations, replayed histories and values the API answers with a 400.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.transport import anthropic_messages
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Message = dict[str, object]


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _body(model: str, messages: list[Message] | None = None, **params: object) -> dict[str, object]:
    route = resolve_route(f"anthropic/{model}", api_key="k")
    history = messages if messages is not None else [{"role": "user", "content": "hi"}]
    return anthropic_messages.prepare(route, history, params).body


def _call(call_id: str, city: str = "Paris") -> dict[str, object]:
    arguments = json.dumps({"city": city})
    return {"id": call_id, "type": "function", "function": {"name": "get_weather", "arguments": arguments}}


def _tool_turn(call_id: str = "call_1", *, text: str = "") -> list[Message]:
    return [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": text, "tool_calls": [_call(call_id)]},
        {"role": "tool", "tool_call_id": call_id, "content": "sunny"},
    ]


def _blocks(body: dict[str, object], index: int) -> list[dict[str, object]]:
    messages = body["messages"]
    assert isinstance(messages, list)
    content = messages[index]["content"]
    assert isinstance(content, list)
    return content


# Dated ids the catalog does not list, so the rules under test come from the model name alone and a snapshot
# refresh cannot move them: a model taking sampling and token budgets, an adaptive one, and the newest generation.
LEGACY = "claude-sonnet-4-5-20991231"
ADAPTIVE = "claude-sonnet-4-6-20991231"
NEWEST = "claude-opus-4-7-20991231"
SAMPLING = {"temperature": 0.2, "top_p": 0.9, "top_k": 40}
_TOOL = {"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object"}}}


class TestSamplingParameters:
    def test_the_newest_generation_gets_none_of_them(self) -> None:
        body = _body(NEWEST, **SAMPLING)
        assert not {"temperature", "top_p", "top_k"} & set(body)

    def test_an_earlier_model_keeps_temperature_and_top_k(self) -> None:
        body = _body(LEGACY, **SAMPLING)
        assert (body["temperature"], body["top_k"]) == (0.2, 40)

    def test_temperature_wins_over_top_p_because_the_api_refuses_both(self) -> None:
        assert "top_p" not in _body(LEGACY, **SAMPLING)

    def test_top_p_alone_is_sent(self) -> None:
        body = _body(LEGACY, top_p=0.9, top_k=40)
        assert (body["top_p"], body["top_k"]) == (0.9, 40)
        assert "temperature" not in body

    def test_extended_thinking_takes_no_explicit_sampling(self) -> None:
        body = _body(LEGACY, reasoning_effort="high", **SAMPLING)
        assert not {"temperature", "top_p", "top_k"} & set(body)


class TestThinking:
    def test_a_pre_adaptive_model_thinks_by_token_budget(self) -> None:
        body = _body(LEGACY, reasoning_effort="high", max_tokens=9000)
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 4096}
        assert "output_config" not in body

    def test_an_adaptive_model_thinks_adaptively_steered_by_effort(self) -> None:
        body = _body(ADAPTIVE, reasoning_effort="high", max_tokens=9000)
        assert body["thinking"] == {"type": "adaptive"}
        assert body["output_config"] == {"effort": "high"}

    @pytest.mark.parametrize(
        ("model", "asked", "sent"),
        [
            (NEWEST, "xhigh", "xhigh"),
            (NEWEST, "max", "max"),
            (ADAPTIVE, "xhigh", "max"),
            (ADAPTIVE, "medium", "medium"),
            (ADAPTIVE, "minimal", "low"),
        ],
    )
    def test_the_effort_is_clamped_to_what_the_model_offers(self, model: str, asked: str, sent: str) -> None:
        assert _body(model, reasoning_effort=asked, max_tokens=9000)["output_config"] == {"effort": sent}

    @pytest.mark.parametrize("effort", ["none", "off", "disabled"])
    def test_a_disabled_effort_sends_no_thinking(self, effort: str) -> None:
        body = _body(ADAPTIVE, reasoning_effort=effort, max_tokens=9000, **SAMPLING)
        assert not {"thinking", "output_config"} & set(body)
        assert body["temperature"] == 0.2

    def test_thinking_is_dropped_when_an_earlier_tool_call_lacks_its_signed_block(self) -> None:
        body = _body(LEGACY, _tool_turn(), reasoning_effort="high", max_tokens=9000)
        assert "thinking" not in body

    def test_an_adaptive_model_keeps_its_effort_when_the_replay_forces_thinking_off(self) -> None:
        body = _body(ADAPTIVE, _tool_turn(), reasoning_effort="high", max_tokens=9000, **SAMPLING)
        assert "thinking" not in body
        assert body["output_config"] == {"effort": "high"}
        assert body["temperature"] == 0.2

    def test_an_explicit_thinking_block_is_sent_as_given(self) -> None:
        explicit = {"type": "enabled", "budget_tokens": 2500}
        body = _body(LEGACY, max_tokens=9000, thinking=explicit, **SAMPLING)
        assert body["thinking"] == explicit
        assert not {"temperature", "top_p", "top_k"} & set(body)

    def test_explicitly_disabled_thinking_leaves_sampling_alone(self) -> None:
        body = _body(LEGACY, thinking={"type": "disabled"}, **SAMPLING)
        assert body["thinking"] == {"type": "disabled"}
        assert body["temperature"] == 0.2

    def test_a_signed_thinking_block_in_the_replay_keeps_thinking_on(self) -> None:
        signed = {"type": "thinking", "thinking": "hmm", "signature": "sig"}
        turns = _tool_turn()
        turns[1]["thinking_blocks"] = [signed]
        body = _body(LEGACY, turns, reasoning_effort="high", max_tokens=9000)
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 4096}
        assert _blocks(body, 1)[0] == signed


class TestMaxTokens:
    def test_an_explicit_limit_is_sent(self) -> None:
        assert _body(NEWEST, max_tokens=300)["max_tokens"] == 300

    def test_the_model_ceiling_answers_a_call_that_states_none(self) -> None:
        register_model(NEWEST, {"provider": "anthropic", "max_output_tokens": 4321})
        assert _body(NEWEST)["max_tokens"] == 4321

    def test_a_model_without_a_ceiling_gets_the_wire_default(self) -> None:
        assert _body(NEWEST)["max_tokens"] == anthropic_messages._DEFAULT_MAX_TOKENS

    @pytest.mark.parametrize("bad", [0, -5, 12.5, "100"])
    def test_a_value_the_api_refuses_falls_back_to_the_ceiling(self, bad: object) -> None:
        register_model(NEWEST, {"provider": "anthropic", "max_output_tokens": 4321})
        assert _body(NEWEST, max_tokens=bad)["max_tokens"] == 4321


class TestToolHistory:
    def test_a_replayed_tool_call_without_tool_definitions_declares_a_placeholder(self) -> None:
        body = _body(LEGACY, _tool_turn())
        assert [t["name"] for t in body["tools"]] == ["dummy_tool"]

    def test_declared_tools_replace_the_placeholder(self) -> None:
        body = _body(LEGACY, _tool_turn(), tools=[_TOOL])
        assert [t["name"] for t in body["tools"]] == ["get_weather"]

    def test_a_history_without_tool_calls_declares_no_tools(self) -> None:
        assert "tools" not in _body(LEGACY)

    def test_an_id_outside_the_accepted_alphabet_is_rewritten_on_the_call_and_its_result(self) -> None:
        body = _body(LEGACY, _tool_turn("functions.get_weather:0@2"))
        call = next(b for b in _blocks(body, 1) if b["type"] == "tool_use")
        result = next(b for b in _blocks(body, 2) if b["type"] == "tool_result")
        assert call["id"] == result["tool_use_id"] == "functions_get_weather_0_2"

    def test_an_empty_id_still_pairs_the_call_with_its_result(self) -> None:
        body = _body(LEGACY, _tool_turn(""))
        call = next(b for b in _blocks(body, 1) if b["type"] == "tool_use")
        result = next(b for b in _blocks(body, 2) if b["type"] == "tool_result")
        assert call["id"] == result["tool_use_id"] == "tool_use_id"

    def test_parallel_results_share_one_user_turn_ahead_of_the_follow_up_text(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "weather?"},
            {"role": "assistant", "content": "", "tool_calls": [_call("a"), _call("b", "Rome")]},
            {"role": "tool", "tool_call_id": "a", "content": "sunny"},
            {"role": "tool", "tool_call_id": "b", "content": "rainy"},
            {"role": "user", "content": "thanks"},
        ]
        kinds = [b["type"] for b in _blocks(_body(LEGACY, turns), 2)]
        assert kinds == ["tool_result", "tool_result", "text"]

    def test_an_empty_tool_result_is_sent_as_an_empty_string(self) -> None:
        turns = _tool_turn()
        turns[2]["content"] = ""
        result = next(b for b in _blocks(_body(LEGACY, turns), 2) if b["type"] == "tool_result")
        assert result["content"] == ""


class TestToolChoice:
    def test_no_choice_is_sent_when_the_caller_states_no_preference(self) -> None:
        assert "tool_choice" not in _body(LEGACY, tools=[_TOOL])

    def test_a_parallel_preference_alone_is_sent(self) -> None:
        body = _body(LEGACY, tools=[_TOOL], parallel_tool_calls=False)
        assert body["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}

    def test_a_required_choice_forces_a_tool(self) -> None:
        body = _body(LEGACY, tools=[_TOOL], tool_choice="required", parallel_tool_calls=True)
        assert body["tool_choice"] == {"type": "any", "disable_parallel_tool_use": False}


class TestBlankText:
    """The API refuses a blank text block and an empty message."""

    def test_a_blank_assistant_text_next_to_a_tool_call_is_dropped(self) -> None:
        body = _body(LEGACY, _tool_turn(text="\n\n"))
        assert [b["type"] for b in _blocks(body, 1)] == ["tool_use"]

    def test_a_blank_assistant_turn_vanishes_and_the_user_messages_around_it_merge(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "  \n"},
            {"role": "user", "content": "thanks"},
        ]
        body = _body(LEGACY, turns)
        assert [m["role"] for m in body["messages"]] == ["user"]
        assert [b["text"] for b in _blocks(body, 0)] == ["hi", "thanks"]

    def test_a_request_of_nothing_but_blank_text_still_has_a_message(self) -> None:
        body = _body(LEGACY, [{"role": "user", "content": "   "}])
        assert _blocks(body, 0) == [{"type": "text", "text": "."}]

    def test_a_blank_system_prompt_is_dropped(self) -> None:
        body = _body(LEGACY, [{"role": "system", "content": " "}, {"role": "user", "content": "hi"}])
        assert "system" not in body or body["system"] == []

    def test_a_blank_part_among_real_ones_is_dropped(self) -> None:
        parts = [{"type": "text", "text": "  "}, {"type": "text", "text": "real"}]
        body = _body(LEGACY, [{"role": "user", "content": parts}])
        assert [b["text"] for b in _blocks(body, 0)] == ["real"]


class TestClosingAssistantMessage:
    """A closing assistant message is a prefill; the API refuses one that ends in whitespace."""

    def test_trailing_whitespace_is_trimmed(self) -> None:
        turns: list[Message] = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello there. \n"}]
        assert _blocks(_body(LEGACY, turns), 1) == [{"type": "text", "text": "Hello there."}]

    def test_an_inner_assistant_message_is_left_alone(self) -> None:
        turns: list[Message] = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello there. "},
            {"role": "user", "content": "go on"},
        ]
        assert _blocks(_body(LEGACY, turns), 1) == [{"type": "text", "text": "Hello there. "}]

    def test_a_closing_assistant_message_with_nothing_to_prefill_is_dropped(self) -> None:
        turns: list[Message] = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": " "}]
        assert [m["role"] for m in _body(LEGACY, turns)["messages"]] == ["user"]


class TestUserIdentifier:
    @pytest.mark.parametrize("opaque", ["u_8f3a", "7c9e6679-7425-40de-944b-e07fc1f90ae7"])
    def test_an_opaque_id_is_sent(self, opaque: str) -> None:
        assert _body(LEGACY, user=opaque)["metadata"] == {"user_id": opaque}

    @pytest.mark.parametrize("personal", ["jane.doe@example.com", "+1 (555) 123-4567", "555-123-4567"])
    def test_an_email_or_phone_number_is_not_sent(self, personal: str) -> None:
        assert "metadata" not in _body(LEGACY, user=personal)
