"""Gemini generate edges: generation options, tool choice, declarations the API accepts, and frames to skip."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from myrm_agent_harness.toolkits.llms.transport import gemini_generate
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError, resolve_route

Body = dict[str, object]

_MODEL = "gemini/gemini-2.5-pro"
_NAMED = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Weather",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}


def _body(**params: object) -> Body:
    route = resolve_route(_MODEL, api_key="k")
    body = gemini_generate.prepare(route, [{"role": "user", "content": "hi"}], params).body
    assert body is not None
    return dict(body)


class TestGenerationConfig:
    def test_a_stop_string_becomes_a_one_entry_list(self) -> None:
        assert _body(stop="END")["generationConfig"] == {"stopSequences": ["END"]}

    def test_a_stop_list_keeps_only_strings_and_an_empty_one_sends_nothing(self) -> None:
        assert _body(stop=["a", 3, "b"])["generationConfig"] == {"stopSequences": ["a", "b"]}
        assert "generationConfig" not in _body(stop=[])

    def test_a_route_without_an_endpoint_is_refused_with_a_reason(self) -> None:
        route = replace(resolve_route(_MODEL, api_key="k"), base_url=None)

        with pytest.raises(UnsupportedProviderError, match="needs an api_base"):
            gemini_generate.prepare(route, [{"role": "user", "content": "hi"}], {})


class TestTools:
    @pytest.mark.parametrize(
        ("choice", "expected"),
        [
            (None, {"functionCallingConfig": {"mode": "AUTO"}}),
            ("auto", {"functionCallingConfig": {"mode": "AUTO"}}),
            ("required", {"functionCallingConfig": {"mode": "ANY"}}),
            ("none", {"functionCallingConfig": {"mode": "NONE"}}),
            (
                {"type": "function", "function": {"name": "get_weather"}},
                {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["get_weather"]}},
            ),
        ],
        ids=["default", "auto", "required", "none", "named"],
    )
    def test_tool_choice_maps_onto_the_function_calling_modes(self, choice: object, expected: Body) -> None:
        assert _body(tools=[_NAMED], tool_choice=choice)["toolConfig"] == expected

    @pytest.mark.parametrize(
        "choice", [{"type": "function"}, "sometimes", 7], ids=["nameless", "unknown-text", "number"]
    )
    def test_a_choice_the_api_has_no_mode_for_is_left_to_its_default(self, choice: object) -> None:
        assert "toolConfig" not in _body(tools=[_NAMED], tool_choice=choice)

    def test_only_named_functions_are_declared_and_an_empty_schema_sends_no_parameters(self) -> None:
        bare = {"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}
        tools = [
            _NAMED,
            {"type": "function", "function": {"description": "nameless"}},
            {"type": "web_search"},
            "junk",
            bare,
        ]

        declared = _body(tools=tools)["tools"]

        assert [d["name"] for d in declared[0]["functionDeclarations"]] == ["get_weather", "ping"]  # type: ignore[index]
        assert "parameters" not in declared[0]["functionDeclarations"][1]  # type: ignore[index]

    def test_no_declared_function_means_no_tool_section_and_no_tool_config(self) -> None:
        body = _body(tools=[{"type": "function", "function": {"description": "nameless"}}], tool_choice="required")

        assert "tools" not in body
        assert "toolConfig" not in body


class TestStreamFrames:
    def _decoder(self) -> gemini_generate.GeminiStreamDecoder:
        return gemini_generate.GeminiStreamDecoder("gemini", "gemini-2.5-pro")

    @pytest.mark.parametrize("data", ["keep-alive", "[1]", "3", "null"], ids=["text", "array", "number", "null"])
    def test_a_frame_that_is_not_an_object_is_skipped(self, data: str) -> None:
        decoder = self._decoder()

        assert decoder.feed(None, data) == []
        assert decoder.done is False

    def test_an_error_frame_raises_instead_of_ending_quietly(self) -> None:
        with pytest.raises(LLMAnswerError):
            self._decoder().feed(None, json.dumps({"error": {"code": 429, "message": "quota"}}))

    def test_a_frame_with_no_new_text_and_no_finish_yields_nothing(self) -> None:
        frame = {"candidates": [{"content": {"role": "model", "parts": [{"text": ""}]}}]}

        assert self._decoder().feed(None, json.dumps(frame)) == []
