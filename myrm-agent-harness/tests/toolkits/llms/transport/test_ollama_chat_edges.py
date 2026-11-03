"""Ollama chat edges: thinking levels, structured output, history it cannot take, and stream lines it must skip."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from myrm_agent_harness.toolkits.llms.transport import ollama_chat
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError, resolve_route

Message = dict[str, object]


def _route(model: str = "llama3.1") -> Route:
    return resolve_route(f"ollama/{model}")


def _body(messages: list[Message] | None = None, *, model: str = "llama3.1", **params: object) -> dict[str, object]:
    request = ollama_chat.prepare(_route(model), messages or [{"role": "user", "content": "hi"}], params)
    assert request.body is not None
    return dict(request.body)


def _sent_messages(body: dict[str, object]) -> list[dict[str, object]]:
    messages = body["messages"]
    assert isinstance(messages, list)
    return messages


class TestRequest:
    def test_a_route_without_an_endpoint_is_refused_with_a_reason(self) -> None:
        route = replace(_route(), base_url=None)

        with pytest.raises(UnsupportedProviderError, match="needs an api_base"):
            ollama_chat.prepare(route, [{"role": "user", "content": "hi"}], {})

    def test_bare_strings_in_a_part_list_are_joined_into_the_text(self) -> None:
        body = _body([{"role": "user", "content": ["a", {"type": "text", "text": "b"}]}])

        assert _sent_messages(body) == [{"role": "user", "content": "ab"}]

    def test_a_remote_image_is_dropped_with_a_warning_because_only_inline_data_is_accepted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        image = {"type": "image_url", "image_url": {"url": "https://example.test/cat.png"}}
        with caplog.at_level(logging.WARNING):
            body = _body([{"role": "user", "content": [{"type": "text", "text": "look"}, image]}])

        assert _sent_messages(body) == [{"role": "user", "content": "look"}]
        assert "remote image" in caplog.text

    def test_a_part_ollama_has_no_slot_for_is_dropped_with_a_warning_naming_its_type(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        parts = [{"type": "text", "text": "hi"}, {"type": "input_audio", "input_audio": {}}, 42]
        with caplog.at_level(logging.WARNING):
            body = _body([{"role": "user", "content": parts}])

        assert _sent_messages(body) == [{"role": "user", "content": "hi"}]
        assert "input_audio" in caplog.text

    def test_a_tool_result_whose_call_is_unknown_is_sent_without_a_tool_name(self) -> None:
        body = _body([{"role": "user", "content": "x"}, {"role": "tool", "tool_call_id": "nope", "content": "42"}])

        assert _sent_messages(body)[1] == {"role": "tool", "content": "42"}

    def test_replayed_calls_carry_decoded_arguments_and_the_tool_name_reaches_its_result(self) -> None:
        calls = [
            {"id": "c0", "type": "function"},
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"city": "Paris"}'}},
            {"id": "c2", "type": "function", "function": {"name": "g", "arguments": "{not json"}},
        ]
        body = _body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "tool_calls": calls},
                {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
            ]
        )

        sent = _sent_messages(body)
        assert sent[1]["tool_calls"] == [
            {"function": {"name": "f", "arguments": {"city": "Paris"}}},
            {"function": {"name": "g", "arguments": {}}},
        ]
        assert sent[2] == {"role": "tool", "content": "sunny", "tool_name": "f"}

    def test_a_single_stop_string_becomes_the_stop_list_inside_options(self) -> None:
        assert _body(stop="END")["options"] == {"stop": ["END"]}

    def test_json_mode_asks_for_json_output(self) -> None:
        assert _body(response_format={"type": "json_object"})["format"] == "json"

    @pytest.mark.parametrize("effort", ["none", "off", "disabled"])
    def test_a_disabled_reasoning_effort_switches_thinking_off(self, effort: str) -> None:
        assert _body(reasoning_effort=effort)["think"] is False

    @pytest.mark.parametrize(
        ("effort", "level"), [("minimal", "low"), ("medium", "medium"), ("xhigh", "high")], ids=["low", "mid", "high"]
    )
    def test_gpt_oss_takes_a_thinking_level_where_other_models_take_a_switch(self, effort: str, level: str) -> None:
        assert _body(model="gpt-oss:20b", reasoning_effort=effort)["think"] == level
        assert _body(reasoning_effort=effort)["think"] is True


class TestStreamLines:
    def _decoder(self) -> ollama_chat.OllamaStreamDecoder:
        return ollama_chat.OllamaStreamDecoder("ollama", "llama3.1")

    @pytest.mark.parametrize("line", ["keep-alive", "[1, 2]", "42"], ids=["text", "array", "number"])
    def test_a_line_that_is_not_an_object_is_skipped(self, line: str) -> None:
        decoder = self._decoder()

        assert decoder.feed(None, line) == []
        assert decoder.done is False

    def test_a_line_with_nothing_new_yields_no_chunk_until_the_done_line_arrives(self) -> None:
        decoder = self._decoder()

        assert decoder.feed(None, json.dumps({"message": {"role": "assistant", "content": ""}, "done": False})) == []
        (closing,) = decoder.feed(None, json.dumps({"done": True, "done_reason": "stop", "prompt_eval_count": 3}))
        assert closing["choices"][0]["finish_reason"] == "stop"  # type: ignore[index]
        assert decoder.done is True

    def test_an_error_line_raises_instead_of_ending_the_stream_quietly(self) -> None:
        with pytest.raises(LLMAnswerError):
            self._decoder().feed(None, json.dumps({"error": "model not found"}))

    def test_a_call_without_a_function_leaves_no_gap_that_a_later_line_would_collide_with(self) -> None:
        decoder = self._decoder()
        first = {"message": {"tool_calls": [{"id": "x"}, {"function": {"name": "f", "arguments": {"a": 1}}}]}}
        second = {"message": {"tool_calls": [{"function": {"name": "g", "arguments": {"b": 2}}}]}}

        (chunk_one,) = decoder.feed(None, json.dumps(first))
        (chunk_two,) = decoder.feed(None, json.dumps(second))

        def calls(chunk: dict[str, object]) -> list[tuple[int, str, str]]:
            delta = chunk["choices"][0]["delta"]  # type: ignore[index]
            return [(c["index"], c["function"]["name"], c["function"]["arguments"]) for c in delta["tool_calls"]]

        assert calls(chunk_one) == [(0, "f", '{"a": 1}')]
        assert calls(chunk_two) == [(1, "g", '{"b": 2}')], "two calls must never share an index: they would merge"
