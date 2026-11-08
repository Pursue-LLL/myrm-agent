"""Anthropic Messages request edges: parts and tool declarations the API takes in another shape, or not at all.

Each case is something a caller can hand the transport that must come out as a valid request, or be left out with a
reason, instead of reaching the API as a 400.
"""

from __future__ import annotations

import logging
from dataclasses import replace

import pytest

from myrm_agent_harness.toolkits.llms.catalog import store
from myrm_agent_harness.toolkits.llms.transport import anthropic_messages
from myrm_agent_harness.toolkits.llms.transport.anthropic_thinking import Thinking, request_thinking
from myrm_agent_harness.toolkits.llms.transport.capabilities import ClaudeTraits
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError, resolve_route

Message = dict[str, object]

# A dated id the catalog does not list, so only the model name decides the rules.
MODEL = "claude-sonnet-4-5-20991231"
_TOOL = {"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object"}}}


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _prepare(messages: list[Message], **params: object) -> anthropic_messages.PreparedRequest:
    return anthropic_messages.prepare(resolve_route(f"anthropic/{MODEL}", api_key="k"), messages, params)


def _body(messages: list[Message] | None = None, **params: object) -> dict[str, object]:
    body = _prepare(messages or [{"role": "user", "content": "hi"}], **params).body
    assert body is not None
    return dict(body)


def _first_turn(body: dict[str, object]) -> list[dict[str, object]]:
    turns = body["messages"]
    assert isinstance(turns, list)
    return turns[0]["content"]


class TestContentParts:
    def test_a_pdf_file_part_is_a_document_block_that_keeps_its_cache_marker(self) -> None:
        pdf = {
            "type": "file",
            "file": {"file_data": "data:application/pdf;base64,JVBERg=="},
            "cache_control": {"type": "ephemeral"},
        }
        body = _body([{"role": "user", "content": [{"type": "text", "text": "summarise"}, pdf]}])

        assert _first_turn(body)[1] == {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": "JVBERg=="},
            "cache_control": {"type": "ephemeral"},
        }

    @pytest.mark.parametrize(
        "part",
        [
            {"type": "file", "file": {"file_data": "https://example.test/a.pdf"}},
            {"type": "file", "file": "not-a-mapping"},
            {"type": "image_url", "image_url": {"url": ""}},
            {"type": "image_url"},
        ],
        ids=["remote-pdf", "file-not-a-mapping", "empty-image-url", "image-without-url"],
    )
    def test_a_part_the_api_cannot_take_is_left_out_rather_than_sent_malformed(self, part: Message) -> None:
        body = _body([{"role": "user", "content": [{"type": "text", "text": "hi"}, part]}])

        assert _first_turn(body) == [{"type": "text", "text": "hi"}]

    def test_bare_strings_in_a_part_list_are_text_and_blank_ones_or_stray_values_vanish(self) -> None:
        body = _body([{"role": "user", "content": ["first", "   ", {"type": "text", "text": "second"}, 42]}])

        assert _first_turn(body) == [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]

    def test_an_unsupported_part_type_is_dropped_and_named_in_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        parts = [{"type": "text", "text": "hi"}, {"type": "input_audio", "input_audio": {}}]
        with caplog.at_level(logging.WARNING):
            body = _body([{"role": "user", "content": parts}])

        assert _first_turn(body) == [{"type": "text", "text": "hi"}]
        assert "input_audio" in caplog.text


class TestHistory:
    def test_a_call_without_a_function_is_skipped_and_unreadable_arguments_become_an_empty_object(self) -> None:
        calls = [
            {"id": "c0", "type": "function"},
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{not json"}},
        ]
        body = _body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "tool_calls": calls},
                {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            ]
        )

        messages = body["messages"]
        assert isinstance(messages, list)
        assert messages[1]["content"] == [{"type": "tool_use", "id": "c1", "name": "f", "input": {}}]

    def test_a_blank_closing_assistant_message_is_dropped_instead_of_sent_as_an_empty_prefill(self) -> None:
        body = _body([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "   "}])

        assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_a_prefill_loses_the_whitespace_the_api_refuses_to_end_on(self) -> None:
        body = _body([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Answer: "}])

        messages = body["messages"]
        assert isinstance(messages, list)
        assert messages[-1] == {"role": "assistant", "content": [{"type": "text", "text": "Answer:"}]}

    def test_a_closing_assistant_message_that_ends_in_a_tool_call_is_sent_untouched(self) -> None:
        call = {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        body = _body(
            [{"role": "user", "content": "x"}, {"role": "assistant", "content": "Let me look ", "tool_calls": [call]}]
        )

        messages = body["messages"]
        assert isinstance(messages, list)
        assert messages[-1]["content"] == [
            {"type": "text", "text": "Let me look "},
            {"type": "tool_use", "id": "c1", "name": "f", "input": {}},
        ]

    @pytest.mark.parametrize(
        "content",
        [None, [], [{"type": "image_url", "image_url": {"url": ""}}]],
        ids=["no-content", "empty-list", "only-unusable-parts"],
    )
    def test_a_tool_result_with_nothing_to_show_is_sent_without_content(self, content: object) -> None:
        call = {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        body = _body(
            [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "", "tool_calls": [call]},
                {"role": "tool", "tool_call_id": "c1", "content": content},
            ]
        )

        messages = body["messages"]
        assert isinstance(messages, list)
        assert messages[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1"}]}

    def test_a_message_of_a_role_the_api_does_not_know_is_ignored(self) -> None:
        body = _body([{"role": "user", "content": "hi"}, {"role": "function", "name": "f", "content": "legacy"}])

        assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


class TestToolDeclarations:
    def test_a_server_tool_passes_through_next_to_the_callers_functions(self) -> None:
        server_tool = {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
        body = _body(tools=[_TOOL, server_tool, {"type": "function"}])

        tools = body["tools"]
        assert isinstance(tools, list)
        assert [t["name"] for t in tools] == ["get_weather", "web_search"]
        assert tools[1] == server_tool

    def test_the_native_search_option_adds_the_search_tool_with_its_use_limit(self) -> None:
        body = _body(web_search_options={"max_uses": 3})

        assert body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]

    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            ("none", {"type": "none"}),
            ("required", {"type": "any", "disable_parallel_tool_use": False}),
            (
                {"type": "function", "function": {"name": "get_weather"}},
                {"type": "tool", "name": "get_weather", "disable_parallel_tool_use": False},
            ),
            ({"name": "get_weather"}, {"type": "tool", "name": "get_weather", "disable_parallel_tool_use": False}),
            ({"type": "function"}, {"type": "auto", "disable_parallel_tool_use": False}),
        ],
        ids=["none", "required", "named-openai-shape", "named-flat", "nameless-mapping"],
    )
    def test_tool_choice_maps_onto_the_messages_api_forms(self, choice: object, expected: dict[str, object]) -> None:
        assert _body(tools=[_TOOL], tool_choice=choice)["tool_choice"] == expected

    def test_a_tool_choice_of_an_unknown_kind_is_left_to_the_apis_default(self) -> None:
        assert "tool_choice" not in _body(tools=[_TOOL], tool_choice=7)


class TestRequestOptions:
    def test_a_single_stop_string_becomes_the_stop_sequence_list(self) -> None:
        assert _body(stop="END")["stop_sequences"] == ["END"]

    def test_caller_beta_flags_stay_next_to_the_one_structured_output_needs(self) -> None:
        schema = {"type": "json_schema", "json_schema": {"name": "r", "schema": {"type": "object", "properties": {}}}}
        request = _prepare(
            [{"role": "user", "content": "hi"}],
            response_format=schema,
            extra_headers={"Anthropic-Beta": "prompt-caching-2024-07-31"},
        )

        flags = request.headers["Anthropic-Beta"].split(",")
        assert flags == ["prompt-caching-2024-07-31", "structured-outputs-2025-11-13"]

    def test_a_json_schema_format_that_carries_no_schema_asks_for_no_structured_output(self) -> None:
        request = _prepare([{"role": "user", "content": "hi"}], response_format={"type": "json_schema"})

        assert request.body is not None
        assert "output_format" not in request.body
        assert not any(name.lower() == "anthropic-beta" for name in request.headers), "no beta flag without the feature"

    def test_a_route_without_an_endpoint_is_refused_with_a_reason(self) -> None:
        route = replace(resolve_route(f"anthropic/{MODEL}", api_key="k"), base_url=None)

        with pytest.raises(UnsupportedProviderError, match="needs an api_base"):
            anthropic_messages.prepare(route, [{"role": "user", "content": "hi"}], {})

    def test_a_route_without_a_key_sends_no_credentials(self) -> None:
        route = replace(resolve_route(f"anthropic/{MODEL}", api_key="k"), api_key=None)

        request = anthropic_messages.prepare(route, [{"role": "user", "content": "hi"}], {})

        assert {name.lower() for name in request.headers} == {"anthropic-version"}


class TestEffortClamp:
    @pytest.mark.parametrize("asked", ["max", "xhigh", "high"])
    def test_a_model_offering_neither_higher_level_gets_high(self, asked: str) -> None:
        traits = ClaudeTraits(adaptive_thinking=True, xhigh_effort=False, max_effort=False)

        thinking = request_thinking({"reasoning_effort": asked}, traits, [])

        assert thinking == Thinking({"type": "adaptive"}, "high")
