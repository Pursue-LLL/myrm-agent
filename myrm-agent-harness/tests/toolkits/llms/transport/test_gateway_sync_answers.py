"""The synchronous call path reads a gateway's answer like the asynchronous one: the facade shapes both.

``test_gateway_answer_shapes`` replays the odd answers through ``ainvoke``/``astream``; the sync paths are separate
branches of the facade (``completion``/``stream``), so each of them is held to the same few readings here.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMResponseError
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker

from .gateway_bodies import (
    CALL,
    STRING_USAGE,
    TOOL_MESSAGE,
    Body,
    answer,
    chat_model,
    chunk,
    failed_choice,
    sse_body,
    usage_of,
    usage_only,
)

Serve = Callable[[bytes, str], None]
_FAILURES = (LLMAnswerError, LLMResponseError)


def _invoke(serve_answer: Serve, body: Body) -> AIMessage:
    serve_answer(json.dumps(body).encode(), "application/json")
    return chat_model(streaming=False).invoke([HumanMessage(content="hi")])


def _stream_all(serve_answer: Serve, *frames: Body | str) -> AIMessageChunk:
    serve_answer(sse_body(*frames), "text/event-stream")
    message: AIMessageChunk | None = None
    for part in chat_model(streaming=True).stream([HumanMessage(content="hi")]):
        message = part if message is None else message + part
    assert message is not None
    return message


class TestWholeAnswers:
    def test_usage_a_gateway_wrote_as_text_is_recorded_as_numbers(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        assert _invoke(serve_answer, answer(usage=STRING_USAGE)).content == "hello"

        assert usage_of(tracker) == (11, 7, 18)

    def test_a_gateway_that_reports_no_usage_leaves_no_usage_event_and_the_call_still_answers(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        assert _invoke(serve_answer, answer(usage=None)).content == "hello"

        assert usage_of(tracker) is None

    @pytest.mark.parametrize(
        ("word", "finish"),
        [("end_turn", "stop"), ("max_tokens", "length"), ("SAFETY", "content_filter"), ("something_new", "stop")],
    )
    def test_a_finish_word_of_another_vendor_is_read_as_openais(
        self, word: str, finish: str, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        _invoke(serve_answer, answer(finish=word))

        assert tracker.last_finish_reason == finish

    def test_a_tool_call_is_what_ended_an_answer_that_calls_one(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = _invoke(serve_answer, answer(TOOL_MESSAGE, finish="stop"))

        assert [(c["name"], c["args"]) for c in message.tool_calls] == [("get_weather", {"city": "Tokyo"})]
        assert tracker.last_finish_reason == "tool_calls"

    @pytest.mark.parametrize(
        ("body", "kind"),
        [
            ({"error": {"message": "The server had an error", "type": "server_error"}}, ErrorKind.OVERLOADED),
            ({"error": {"message": "Rate limit reached", "type": "rate_limit_exceeded"}}, ErrorKind.RATE_LIMIT),
            ({"choices": None, "base_resp": {"status_code": 1004, "status_msg": "login fail"}}, ErrorKind.AUTH),
            (failed_choice({"code": 502, "message": "Provider returned error"}), ErrorKind.OVERLOADED),
            (answer({"content": "part"}, finish="insufficient_system_resource"), ErrorKind.OVERLOADED),
            ({"id": "c1", "choices": []}, ErrorKind.OVERLOADED),
        ],
        ids=["server-error", "rate-limit", "base-resp", "failed-choice", "deepseek-no-resource", "no-choice"],
    )
    def test_a_failure_sent_with_a_200_status_raises_and_is_classified(
        self, body: Body, kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            _invoke(serve_answer, body)

        assert classify_error(caught.value) == kind


class TestStreams:
    def test_usage_on_a_chunk_without_choices_is_recorded_once_as_numbers(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = _stream_all(
            serve_answer,
            chunk({"role": "assistant", "content": "hel"}),
            chunk({"content": "lo"}),
            chunk({}, "stop"),
            usage_only(STRING_USAGE, choices=None),
        )

        assert message.content == "hello"
        assert usage_of(tracker) == (11, 7, 18)
        assert tracker.last_finish_reason == "stop"

    def test_tool_calls_survive_a_finish_word_of_another_vendor(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = _stream_all(
            serve_answer,
            chunk({"role": "assistant", "tool_calls": [{"index": 0, **CALL}]}),
            chunk({}, "tool_use"),
        )

        assert [(c["name"], c["args"]) for c in message.tool_calls] == [("get_weather", {"city": "Tokyo"})]
        assert tracker.last_finish_reason == "tool_calls"

    def test_a_bracketed_marker_between_payloads_is_not_content(self, serve_answer: Serve) -> None:
        frames: list[Body | str] = [chunk({"content": "hel"}), "[PING]", chunk({"content": "lo"}), chunk({}, "stop")]

        assert _stream_all(serve_answer, *frames).content == "hello"

    @pytest.mark.parametrize(
        ("frames", "kind"),
        [
            ([chunk({"content": "hel"}), chunk({"content": ""}, "error", error={"code": 502})], ErrorKind.OVERLOADED),
            (
                [chunk({"content": "hel"}), {"error": {"message": "slow", "type": "rate_limit_exceeded"}}],
                ErrorKind.RATE_LIMIT,
            ),
            ([chunk({"content": "hel"}), chunk({}, "aborted")], ErrorKind.OVERLOADED),
            ([chunk({"content": "hel"}), '{"id": "c1", "choices": [{"index": 0, "delta": {"con'], ErrorKind.OVERLOADED),
        ],
        ids=["error-with-choices", "rate-limit", "deepseek-aborted", "corrupted-frame"],
    )
    def test_a_failure_in_the_middle_of_the_answer_raises_instead_of_ending_it(
        self, frames: list[Body | str], kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            _stream_all(serve_answer, *frames)

        assert classify_error(caught.value) == kind
