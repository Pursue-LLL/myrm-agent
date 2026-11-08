"""Tests for Responses wire params builder."""

import pytest

from myrm_agent_harness.toolkits.llms.adapters.wire.params import build_responses_kwargs

_USER = [{"role": "user", "content": "hi"}]


def test_build_responses_kwargs_passes_include_from_extra_body() -> None:
    kwargs = build_responses_kwargs(
        [{"role": "user", "content": "hi"}],
        {
            "model": "openai/muse-spark-1.2-contributor",
            "extra_body": {
                "reasoning": {"effort": "low"},
                "include": ["reasoning.encrypted_content"],
            },
        },
    )
    assert kwargs["include"] == ["reasoning.encrypted_content"]
    assert kwargs["reasoning"] == {"effort": "low"}


def test_build_responses_kwargs_maps_optional_fields() -> None:
    kwargs = build_responses_kwargs(
        [
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "hello"},
        ],
        {
            "model": "openai/muse-spark-1.2-contributor",
            "max_tokens": 256,
            "reasoning_effort": "medium",
            "api_key": "sk-test",
            "api_base": "https://opencode.ai/zen/go/v1",
            "stream": True,
            "tools": [{"type": "function", "function": {"name": "web_search"}}],
            "tool_choice": "auto",
            "temperature": 0.2,
            "top_p": 0.9,
            "timeout": 30,
            "extra_headers": {"X-Test": "1"},
        },
    )
    assert kwargs["instructions"] == "Be concise"
    assert kwargs["max_output_tokens"] == 512
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert kwargs["stream"] is True
    assert kwargs["tools"][0]["function"]["name"] == "web_search"
    assert kwargs["tool_choice"] == "auto"
    assert kwargs["temperature"] == 0.2
    assert kwargs["top_p"] == 0.9
    assert kwargs["timeout"] == 30
    assert kwargs["extra_headers"] == {"X-Test": "1"}


def test_build_responses_kwargs_uses_timeout_param() -> None:
    kwargs = build_responses_kwargs([{"role": "user", "content": "hi"}], {"model": "m", "timeout": 42})
    assert kwargs["timeout"] == 42


class TestToolChoice:
    def test_a_named_function_takes_the_flat_responses_form(self) -> None:
        choice = {"type": "function", "function": {"name": "get_weather"}}

        kwargs = build_responses_kwargs(_USER, {"model": "m", "tool_choice": choice})

        assert kwargs["tool_choice"] == {"type": "function", "name": "get_weather"}

    @pytest.mark.parametrize(
        "choice",
        ["required", "none", {"type": "function", "name": "get_weather"}, {"type": "function", "function": {}}],
        ids=["required", "none", "already-flat", "function-without-name"],
    )
    def test_every_other_choice_goes_through_untouched(self, choice: object) -> None:
        assert build_responses_kwargs(_USER, {"model": "m", "tool_choice": choice})["tool_choice"] == choice


class TestResponseFormat:
    def _text(self, response_format: object) -> object:
        return build_responses_kwargs(_USER, {"model": "m", "response_format": response_format}).get("text")

    def test_json_mode_maps_one_to_one(self) -> None:
        assert self._text({"type": "json_object"}) == {"format": {"type": "json_object"}}

    def test_a_json_schema_keeps_its_name_schema_and_strictness(self) -> None:
        schema = {"type": "object", "properties": {"city": {"type": "string"}}}

        text = self._text({"type": "json_schema", "json_schema": {"name": "place", "schema": schema, "strict": True}})

        assert text == {"format": {"type": "json_schema", "name": "place", "schema": schema, "strict": True}}

    def test_a_schema_without_name_or_strictness_gets_the_defaults(self) -> None:
        text = self._text({"type": "json_schema", "json_schema": {"schema": {"type": "object"}}})

        assert text == {
            "format": {"type": "json_schema", "name": "response", "schema": {"type": "object"}, "strict": False}
        }

    @pytest.mark.parametrize(
        "response_format",
        [
            "json_object",
            {"type": "text"},
            {"type": "json_schema"},
            {"type": "json_schema", "json_schema": {"name": "x"}},
            {"type": "json_schema", "json_schema": {"schema": "not a schema"}},
        ],
        ids=["not-a-mapping", "plain-text", "no-spec", "spec-without-schema", "schema-not-a-mapping"],
    )
    def test_anything_the_endpoint_cannot_enforce_is_not_sent(self, response_format: object) -> None:
        assert self._text(response_format) is None
