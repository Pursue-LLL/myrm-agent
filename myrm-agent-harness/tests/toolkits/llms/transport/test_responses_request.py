"""Responses endpoint: where a request goes, what it carries, and how the event stream is read."""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.llms.transport import openai_chat, openai_responses
from myrm_agent_harness.toolkits.llms.transport.errors import LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError, resolve_route

_AZURE = "https://resource.openai.azure.com"


def _prepare(model: str, *, api_base: str | None = None, **params: object) -> PreparedRequest:
    route = resolve_route(model, api_key="k", api_base=api_base)
    return openai_responses.prepare(route, {"input": "hi", **params})


def _body(request: PreparedRequest) -> dict[str, object]:
    assert request.body is not None
    return dict(request.body)


class TestRequest:
    def test_a_provider_without_a_responses_endpoint_is_refused_by_name(self) -> None:
        with pytest.raises(UnsupportedProviderError, match="Provider 'deepseek' has no Responses endpoint"):
            _prepare("deepseek/deepseek-chat")

    def test_the_stream_flag_is_sent_only_when_streaming(self) -> None:
        assert "stream" not in _body(_prepare("openai/gpt-5.4", stream=False))
        request = _prepare("openai/gpt-5.4", stream=True)
        assert _body(request)["stream"] is True
        assert request.stream is True

    def test_xai_serves_native_search_as_a_tool_next_to_the_callers_tools(self) -> None:
        function = {"type": "function", "name": "f", "parameters": {"type": "object"}}

        body = _body(_prepare("xai/grok-4", tools=[function], web_search_options={"search_context_size": "low"}))

        assert body["tools"] == [function, {"type": "web_search"}]
        assert "web_search_options" not in body

    def test_xai_search_works_without_any_other_tool(self) -> None:
        assert _body(_prepare("xai/grok-4", web_search_options={}))["tools"] == [{"type": "web_search"}]

    def test_a_provider_without_a_search_tool_ignores_the_option_instead_of_sending_it(self) -> None:
        body = _body(_prepare("openai/gpt-5.4", web_search_options={"search_context_size": "low"}))

        assert "web_search_options" not in body
        assert "tools" not in body


class TestAzureAndOrganization:
    def test_azure_addresses_the_model_in_the_body_and_defaults_the_preview_api(self) -> None:
        request = _prepare("azure/gpt-5.4", api_base=_AZURE)

        assert request.url == f"{_AZURE}/openai/responses"
        assert dict(request.query) == {"api-version": "preview"}
        assert request.headers["api-key"] == "k"
        assert _body(request)["model"] == "gpt-5.4"

    def test_azure_takes_the_callers_api_version(self) -> None:
        request = _prepare("azure/gpt-5.4", api_base=_AZURE, api_version="2025-03-01-preview")

        assert dict(request.query) == {"api-version": "2025-03-01-preview"}

    def test_the_organization_header_goes_only_to_openai_itself(self) -> None:
        route = resolve_route("openai/gpt-5.4", api_key="k")
        other = resolve_route("groq/llama-3.3-70b-versatile", api_key="k")
        messages = [{"role": "user", "content": "hi"}]

        assert openai_chat.prepare(route, messages, {"organization": "org-1"}).headers["OpenAI-Organization"] == "org-1"
        assert "OpenAI-Organization" not in openai_chat.prepare(other, messages, {"organization": "org-1"}).headers


class TestEventDecoder:
    def _decoder(self) -> openai_responses.ResponsesEventDecoder:
        return openai_responses.ResponsesEventDecoder("openai")

    def test_the_done_marker_ends_the_stream_without_an_event(self) -> None:
        decoder = self._decoder()

        assert decoder.feed(None, " [DONE] \n") == []
        assert decoder.done is True

    @pytest.mark.parametrize("data", ["{broken", "[1, 2]", "7", "null"], ids=["not-json", "array", "number", "null"])
    def test_a_frame_that_is_not_an_event_object_is_skipped(self, data: str) -> None:
        decoder = self._decoder()

        assert decoder.feed("response.output_text.delta", data) == []
        assert decoder.done is False

    @pytest.mark.parametrize("kind", ["response.completed", "response.failed", "response.incomplete"])
    def test_every_terminal_event_ends_the_stream_and_is_still_delivered(self, kind: str) -> None:
        decoder = self._decoder()
        event = {"type": kind, "response": {"id": "resp_1"}}

        assert decoder.feed(None, json.dumps(event)) == [event]
        assert decoder.done is True

    def test_the_sse_event_name_decides_when_the_payload_carries_no_type(self) -> None:
        decoder = self._decoder()

        decoder.feed("response.completed", json.dumps({"response": {}}))

        assert decoder.done is True

    def test_a_typeless_error_payload_raises_instead_of_ending_quietly(self) -> None:
        with pytest.raises(LLMStreamError):
            self._decoder().feed(None, json.dumps({"error": {"code": "server_error", "message": "boom"}}))

    def test_an_event_that_merely_mentions_an_error_field_is_still_an_event(self) -> None:
        event = {"type": "response.output_text.delta", "delta": "x", "error": None}

        assert self._decoder().feed(None, json.dumps(event)) == [event]

    def test_nothing_is_buffered_so_finishing_adds_nothing(self) -> None:
        assert self._decoder().finish() == []
