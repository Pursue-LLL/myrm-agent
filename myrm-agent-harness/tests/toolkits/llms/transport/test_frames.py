"""A stream frame carries a JSON object, nothing the framing layer may skip, or a payload that was cut off on the way.

Keep-alive text between events is not content and changes nothing; a payload that opens an object and does not parse
is content that never arrived, and ending the answer quietly at that point would hand the agent half of it.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_response,
    gemini_generate,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.http import StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

_CUT_OFF = ['{"a": ', '{"a": 1', "{", '{"a": "cut', '{"id": "c1", "choices": [{"index": 0, "delta": {"con']
_WIRES: dict[str, Callable[[], StreamDecoder]] = {
    "openai-chat": lambda: openai_chat.decoder(resolve_route("openai/gpt-4o", api_key="k")),
    "openai-responses": lambda: openai_responses.decoder(resolve_route("openai/gpt-5", api_key="k")),
    "anthropic": lambda: anthropic_response.decoder(resolve_route("anthropic/claude-sonnet-4-5", api_key="k")),
    "gemini": lambda: gemini_generate.decoder(resolve_route("gemini/gemini-2.5-pro", api_key="k")),
    "ollama": lambda: ollama_chat.decoder(resolve_route("ollama/llama3.1", api_base="http://localhost:11434")),
}


class TestJsonFrame:
    @pytest.mark.parametrize("data", ["", " ", "\n\t", "[DONE]", "  [DONE]\n"])
    def test_a_frame_with_nothing_in_it_is_no_payload(self, data: str) -> None:
        assert json_frame("p", data) is None

    @pytest.mark.parametrize(
        "data",
        [": keep-alive", "ping", "OK", "event: ping", "null", "7", "true", '"text"', "<html>", "data: {}", "done"],
    )
    def test_text_that_does_not_start_like_json_is_skipped(self, data: str) -> None:
        assert json_frame("p", data) is None

    def test_an_object_is_the_payload_whatever_surrounds_it(self) -> None:
        assert json_frame("p", ' \n{"a": [1, {"b": null}]}\r\n') == {"a": [1, {"b": None}]}

    @pytest.mark.parametrize("data", ["[1, 2]", "[]", "[{}]"])
    def test_json_that_is_not_an_object_is_skipped(self, data: str) -> None:
        assert json_frame("p", data) is None

    @pytest.mark.parametrize("data", ["[PING]", "[heartbeat]", "[", "[1, ", "[DONE", "[done]"])
    def test_a_bracketed_marker_or_fragment_is_no_payload_and_is_not_a_corrupted_one(self, data: str) -> None:
        # A payload is an object, so a frame that opens a bracket is a gateway's marker, never a payload cut short.
        assert json_frame("p", data) is None

    @pytest.mark.parametrize("data", _CUT_OFF)
    def test_a_payload_that_was_cut_off_raises_naming_the_provider(self, data: str) -> None:
        with pytest.raises(LLMResponseError, match=r"^p sent a stream frame that is cut off or corrupted$") as caught:
            json_frame("p", data)

        assert caught.value.llm_provider == "p"
        assert isinstance(caught.value.__cause__, json.JSONDecodeError)

    def test_a_cut_off_frame_is_the_providers_fault_and_not_a_model_that_wrote_bad_output(self) -> None:
        with pytest.raises(LLMResponseError) as caught:
            json_frame("p", _CUT_OFF[0])

        # RESPONSE_FORMAT_ERROR would be read as "the model produced invalid JSON": semi-permanent, no repeat.
        assert classify_error(caught.value) == ErrorKind.OVERLOADED


@pytest.mark.parametrize("wire", _WIRES)
class TestEveryWireReadsFramesTheSameWay:
    @pytest.mark.parametrize("data", ["", " ", "keep-alive", ": ping", "[DONE]", "[PING]", "[1, ", "7", "null"])
    def test_a_frame_without_a_payload_is_skipped(self, wire: str, data: str) -> None:
        assert _WIRES[wire]().feed(None, data) == []

    def test_an_event_header_does_not_make_a_frame_without_a_payload_content(self, wire: str) -> None:
        assert _WIRES[wire]().feed("ping", "keep-alive") == []

    @pytest.mark.parametrize("data", _CUT_OFF)
    def test_a_payload_that_was_cut_off_raises_instead_of_ending_the_answer_early(self, wire: str, data: str) -> None:
        with pytest.raises(LLMResponseError, match="cut off or corrupted"):
            _WIRES[wire]().feed(None, data)

    def test_a_frame_that_cuts_off_after_good_ones_still_raises(self, wire: str) -> None:
        decoder = _WIRES[wire]()
        decoder.feed(None, "keep-alive")

        with pytest.raises(LLMResponseError):
            decoder.feed(None, '{"choices": [{"delta": {"content": "par')
