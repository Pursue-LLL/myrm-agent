"""A provider that answers HTTP 200 with a failure: the body or the event is the error the status line did not carry.

Each wire reads the failure the way its provider writes it. What is raised must name the provider, carry the status the
failure stands for (so the agent repeats what is the provider's fault and not what it rejected), and an answer that
merely has an empty ``error`` field is an answer.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_response,
    gemini_generate,
    ollama_chat,
    openai_chat,
    openai_responses,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.http import StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import Route, resolve_route

Payload = dict[str, object]
Parse = Callable[[Route, Payload], Payload]

_OPENAI = resolve_route("openai/gpt-4o", api_key="k")
_RESPONSES = resolve_route("openai/gpt-5", api_key="k")
_ANTHROPIC = resolve_route("anthropic/claude-sonnet-4-5", api_key="k")
_GEMINI = resolve_route("gemini/gemini-2.5-pro", api_key="k")
_OLLAMA = resolve_route("ollama/llama3.1", api_base="http://localhost:11434")
_CHOICE: Payload = {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
_FAILED_CHOICE: Payload = {"index": 0, "message": {"content": ""}, "finish_reason": "error"}


def _cut_off_by(reason: str) -> Payload:
    return {"choices": [{**_FAILED_CHOICE, "finish_reason": reason}]}


def _base_resp(code: object) -> Payload:
    return {"choices": None, "base_resp": {"status_code": code, "status_msg": "refused"}}


class TestAFailureBody:
    @pytest.mark.parametrize(
        ("parse", "route", "body", "status"),
        [
            (openai_chat.parse, _OPENAI, {"error": {"message": "x", "type": "rate_limit_exceeded"}}, 429),
            (openai_chat.parse, _OPENAI, {"error": {"message": "x", "code": "502"}}, 502),
            (openai_chat.parse, _OPENAI, {"error": {"message": "x", "code": 503}, "choices": [_CHOICE]}, 503),
            (openai_chat.parse, _OPENAI, {"error": {"message": "x", "code": 999}}, None),
            (openai_chat.parse, _OPENAI, {"error": "plain text failure"}, None),
            (openai_chat.parse, _OPENAI, _base_resp(1002), 429),
            (openai_chat.parse, _OPENAI, _base_resp(1004), 401),
            (openai_chat.parse, _OPENAI, _base_resp(1008), 402),
            (openai_chat.parse, _OPENAI, _base_resp(2013), 400),
            (openai_chat.parse, _OPENAI, _base_resp(9999), 500),
            (
                openai_chat.parse,
                _OPENAI,
                {"choices": [{**_FAILED_CHOICE, "error": {"message": "x", "code": 502}}]},
                502,
            ),
            (openai_chat.parse, _OPENAI, {"choices": [{**_FAILED_CHOICE, "finish_reason": "Error"}]}, None),
            (openai_chat.parse, _OPENAI, _cut_off_by("insufficient_system_resource"), 503),
            (openai_chat.parse, _OPENAI, _cut_off_by("Aborted"), 503),
            (
                anthropic_response.parse,
                _ANTHROPIC,
                {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
                529,
            ),
            (
                anthropic_response.parse,
                _ANTHROPIC,
                {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}},
                400,
            ),
            (anthropic_response.parse, _ANTHROPIC, {"type": "error", "error": {"message": "unnamed"}}, None),
            (gemini_generate.parse, _GEMINI, {"error": {"code": 429, "message": "quota", "status": "EXHAUSTED"}}, 429),
            (gemini_generate.parse, _GEMINI, {"error": {"code": 400, "message": "bad"}, "candidates": []}, 400),
            (gemini_generate.parse, _GEMINI, {"error": {"message": "unnamed"}}, None),
            (ollama_chat.parse, _OLLAMA, {"error": "model 'x' not found"}, None),
            (ollama_chat.parse, _OLLAMA, {"error": {"message": "x", "code": 500}}, 500),
            (openai_responses.parse, _RESPONSES, {"error": {"message": "bad", "type": "invalid_request_error"}}, 400),
            (openai_responses.parse, _RESPONSES, {"error": {"message": "unnamed"}}, None),
        ],
        ids=[
            "openai-kind",
            "openai-numeric-text-code",
            "openai-error-beside-choices",
            "openai-code-out-of-range",
            "openai-plain-text",
            "minimax-1002",
            "minimax-1004",
            "minimax-1008",
            "minimax-2013",
            "minimax-unlisted",
            "openrouter-failed-choice",
            "openrouter-finish-error-no-detail",
            "deepseek-no-resource",
            "deepseek-aborted",
            "anthropic-overloaded",
            "anthropic-invalid-request",
            "anthropic-unnamed",
            "gemini-quota",
            "gemini-error-with-empty-candidates",
            "gemini-unnamed",
            "ollama-text",
            "ollama-object",
            "responses-kind",
            "responses-unnamed",
        ],
    )
    def test_it_raises_with_the_status_the_failure_stands_for(
        self, parse: Parse, route: Route, body: Payload, status: int | None
    ) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            parse(route, body)

        assert caught.value.status_code == status
        assert caught.value.llm_provider == route.profile.id
        assert str(caught.value).startswith(f"{route.profile.id} answer error: ")

    def test_the_detail_of_a_failed_choice_is_what_the_error_carries(self) -> None:
        detail = {"message": "Provider disconnected", "code": 502}
        with pytest.raises(LLMAnswerError) as caught:
            openai_chat.parse(_OPENAI, {"choices": [{**_FAILED_CHOICE, "error": detail}]})

        assert caught.value.body == {"error": detail}

    @pytest.mark.parametrize(
        ("reason", "detail"),
        [
            ("error", {"message": 'the provider ended the answer with finish reason "error"'}),
            (
                "insufficient_system_resource",
                {
                    "message": 'the provider ended the answer with finish reason "insufficient_system_resource"',
                    "code": 503,
                },
            ),
            ("aborted", {"message": 'the provider ended the answer with finish reason "aborted"', "code": 503}),
        ],
    )
    def test_a_cut_off_without_detail_names_the_finish_reason_and_carries_the_status_it_stands_for(
        self, reason: str, detail: Payload
    ) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            openai_chat.parse(_OPENAI, _cut_off_by(reason))

        assert caught.value.body == {"error": detail}

    def test_a_minimax_failure_carries_its_own_words_and_the_status_it_stands_for(self) -> None:
        with pytest.raises(LLMAnswerError) as caught:
            openai_chat.parse(_OPENAI, _base_resp(1002))

        assert caught.value.body == {"error": {"message": "1002: refused", "code": 429}}

    @pytest.mark.parametrize(
        ("parse", "route", "body"),
        [
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "error": None}),
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "error": ""}),
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "error": {}}),
            # MiniMax's success carries a zero code beside the choices; a failure code beside choices is no failure.
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "base_resp": {"status_code": 0, "status_msg": ""}}),
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "base_resp": {"status_code": 1002}}),
            (openai_chat.parse, _OPENAI, {"choices": [_CHOICE], "base_resp": None}),
            (openai_chat.parse, _OPENAI, {"choices": None, "base_resp": {"status_code": "1002"}}),
            (openai_chat.parse, _OPENAI, {"choices": [{**_CHOICE, "finish_reason": "stop", "error": None}]}),
            (openai_responses.parse, _RESPONSES, {"id": "r", "status": "completed", "output": [], "error": None}),
            # A Response that failed is the adapter's to read: it names the failure in the provider's words.
            (openai_responses.parse, _RESPONSES, {"id": "r", "status": "failed", "error": {"message": "x"}}),
            (openai_responses.parse, _RESPONSES, {"id": "r", "output": [], "error": {"message": "x"}}),
        ],
        ids=[
            "openai-null-error",
            "openai-empty-text-error",
            "openai-empty-object-error",
            "minimax-zero-code",
            "minimax-code-beside-choices",
            "minimax-null-base-resp",
            "minimax-code-as-text",
            "openai-null-choice-error",
            "responses-null-error",
            "responses-failed-status",
            "responses-error-beside-output",
        ],
    )
    def test_an_answer_that_merely_has_an_empty_or_ignorable_error_field_is_handed_on_as_it_is(
        self, parse: Parse, route: Route, body: Payload
    ) -> None:
        assert parse(route, body) is body

    @pytest.mark.parametrize(
        ("parse", "route", "body"),
        [
            (anthropic_response.parse, _ANTHROPIC, {"type": "message", "content": [], "error": None}),
            (gemini_generate.parse, _GEMINI, {"candidates": [{"content": {"parts": []}}], "error": None}),
            (gemini_generate.parse, _GEMINI, {"candidates": [{"content": {"parts": []}}], "error": {"message": "x"}}),
            (ollama_chat.parse, _OLLAMA, {"message": {"content": "hi"}, "done": True, "error": ""}),
        ],
        ids=["anthropic-null-error", "gemini-null-error", "gemini-error-beside-candidates", "ollama-empty-error"],
    )
    def test_an_answer_that_merely_has_an_empty_or_ignorable_error_field_is_converted_like_any_other(
        self, parse: Parse, route: Route, body: Payload
    ) -> None:
        assert parse(route, body)["choices"]


def _openai() -> StreamDecoder:
    return openai_chat.decoder(_OPENAI)


def _anthropic() -> StreamDecoder:
    return anthropic_response.decoder(_ANTHROPIC)


def _gemini() -> StreamDecoder:
    return gemini_generate.decoder(_GEMINI)


def _ollama() -> StreamDecoder:
    return ollama_chat.decoder(_OLLAMA)


def _responses() -> StreamDecoder:
    return openai_responses.decoder(_RESPONSES)


class TestAFailureEventOfAnOpenStream:
    @pytest.mark.parametrize(
        ("make", "event", "frame", "status"),
        [
            (_openai, None, {"error": {"message": "boom"}}, 500),
            (_openai, None, {"error": {"message": "boom", "code": 429}}, 429),
            (_openai, None, {"error": {"message": "slow", "type": "rate_limit_exceeded"}}, 429),
            (_openai, None, {"choices": [_FAILED_CHOICE]}, 500),
            (_openai, None, {"choices": [{**_FAILED_CHOICE, "error": {"message": "cut", "code": 502}}]}, 502),
            (_openai, None, _cut_off_by("insufficient_system_resource"), 503),
            (_openai, None, _cut_off_by("aborted"), 503),
            (_openai, None, {"choices": [], "error": {"message": "boom"}}, 500),
            (_openai, None, _base_resp(1004), 401),
            (_anthropic, "error", {"type": "error", "error": {"type": "overloaded_error", "message": "x"}}, 529),
            (_anthropic, "error", {"type": "error", "error": {"type": "invalid_request_error"}}, 400),
            (_anthropic, "error", {"type": "error", "error": {"message": "unnamed"}}, 500),
            (_gemini, None, {"error": {"code": 429, "message": "quota"}}, 429),
            (_gemini, None, {"error": {"message": "unnamed"}}, 500),
            (_ollama, None, {"error": "boom"}, 500),
            (_responses, None, {"error": {"message": "boom"}}, 500),
            (_responses, None, {"error": {"message": "bad", "code": "429"}}, 429),
        ],
        ids=[
            "openai-unnamed",
            "openai-code",
            "openai-kind",
            "openai-finish-error",
            "openai-failed-choice-detail",
            "deepseek-no-resource",
            "deepseek-aborted",
            "openai-error-beside-empty-choices",
            "minimax-code",
            "anthropic-overloaded",
            "anthropic-invalid-request",
            "anthropic-unnamed",
            "gemini-quota",
            "gemini-unnamed",
            "ollama-text",
            "responses-unnamed",
            "responses-code",
        ],
    )
    def test_the_stream_stops_with_the_status_the_event_stands_for_and_a_fault_when_it_names_none(
        self, make: Callable[[], StreamDecoder], event: str | None, frame: Payload, status: int
    ) -> None:
        decoder = make()
        with pytest.raises(LLMAnswerError) as caught:
            decoder.feed(event, json.dumps(frame))

        assert caught.value.status_code == status
        assert "stream error: " in str(caught.value)

    @pytest.mark.parametrize(
        ("make", "frame", "delivered"),
        [
            (_openai, {"error": None, "choices": [{"index": 0, "delta": {"content": "x"}}]}, 1),
            (_openai, {"error": "", "choices": []}, 1),
            (_openai, {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "error": None}]}, 1),
            (_gemini, {"candidates": [{"content": {"parts": [{"text": "x"}]}}], "error": {"message": "late"}}, 1),
            (_gemini, {"candidates": [], "error": None}, 0),
            (_ollama, {"message": {"content": "x"}, "done": False, "error": ""}, 1),
            (_responses, {"type": "response.failed", "response": {"status": "failed"}, "error": {"message": "x"}}, 1),
            (_responses, {"type": "response.output_text.delta", "delta": "x", "error": None}, 1),
        ],
        ids=[
            "openai-null-error",
            "openai-empty-error",
            "openai-null-choice-error",
            "gemini-error-beside-candidates",
            "gemini-null-error",
            "ollama-empty-error",
            "responses-typed-failure-event",
            "responses-null-error",
        ],
    )
    def test_an_event_that_merely_has_an_empty_or_ignorable_error_field_is_read_as_content(
        self, make: Callable[[], StreamDecoder], frame: Payload, delivered: int
    ) -> None:
        assert len(make().feed(None, json.dumps(frame))) == delivered
