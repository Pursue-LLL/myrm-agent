"""Answers that differ from OpenAI's documented shape, replayed through the whole call path (adapter included).

Gateways put ``null`` where OpenAI puts a number, name a finish reason in another vendor's words, leave out a role, or
answer a failure with HTTP 200. The old stack's litellm layer absorbed all of it; each case here is one such answer,
and what the call turns it into was measured on that stack first, so the expectations below are the behaviour that was
there, except where a case says it is deliberately better (content given as typed parts is read; an ``error`` finish
reason or an ``error`` object next to the choices is a failure and not an answer).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from myrm_agent_harness.toolkits.llms.core.llm import TransportChatModel, create_chat_model
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMResponseError
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker

Body = dict[str, object]
Serve = Callable[[bytes, str], None]
_FAILURES = (LLMAnswerError, LLMResponseError)
_USAGE: Body = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
_CALL: Body = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "get_weather", "arguments": '{"city": "Tokyo"}'},
}
_TOOL_MESSAGE: Body = {"content": None, "tool_calls": [_CALL]}
_STRING_USAGE: Body = {"prompt_tokens": "11", "completion_tokens": "7", "total_tokens": "18"}


def _answer(message: Body | None = None, finish: object = "stop", **top: object) -> Body:
    """One chat.completion that says "hello"; ``message`` overrides fields of the message, ``top`` of the answer."""
    message_fields: Body = {"role": "assistant", "content": "hello", **(message or {})}
    choice: Body = {"index": 0, "message": message_fields, "finish_reason": finish}
    return {"id": "c1", "object": "chat.completion", "model": "m", "choices": [choice], "usage": dict(_USAGE), **top}


def _chunk(delta: Body | None = None, finish: object = None, **top: object) -> Body:
    choice: Body = {"index": 0, "delta": delta if delta is not None else {}, "finish_reason": finish}
    return {"id": "c1", "object": "chat.completion.chunk", "model": "m", "choices": [choice], **top}


def _usage_only(usage: object, **top: object) -> Body:
    return {"id": "c1", "choices": [], "usage": usage, **top}


def _failed_choice(error: Body) -> Body:
    """OpenRouter's way to fail an answer whose upstream broke: the ``error`` finish reason and the detail on the choice."""
    body = _answer({"content": ""}, finish="error")
    body["choices"][0]["error"] = error  # type: ignore[index]
    return body


def _stream(*frames: Body | str) -> bytes:
    lines = [f"data: {frame if isinstance(frame, str) else json.dumps(frame)}\n\n" for frame in frames]
    return "".join([*lines, "data: [DONE]\n\n"]).encode()


def _model(*, streaming: bool) -> TransportChatModel:
    return create_chat_model(
        model="openai/gpt-4o-mini", base_url="http://gateway.test/v1", api_key="k", temperature=0.0, streaming=streaming
    )


async def _invoke(serve_answer: Serve, body: Body) -> AIMessage:
    serve_answer(json.dumps(body).encode(), "application/json")
    return await _model(streaming=False).ainvoke([HumanMessage(content="hi")])


async def _stream_all(serve_answer: Serve, *frames: Body | str) -> AIMessageChunk:
    serve_answer(_stream(*frames), "text/event-stream")
    message: AIMessageChunk | None = None
    async for part in _model(streaming=True).astream([HumanMessage(content="hi")]):
        message = part if message is None else message + part
    assert message is not None
    return message


def _usage(tracker: TokenTracker) -> tuple[int, int, int] | None:
    """What the accounting recorded for the call; ``None`` when the call left no usage event."""
    if tracker.call_count == 0:
        return None
    usage = tracker.usage
    return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens


class TestNonStreamingAnswers:
    @pytest.mark.parametrize(
        ("body", "usage"),
        [
            (_answer(), (11, 7, 18)),
            # Counts a gateway sends as text are the numbers they spell.
            (_answer(usage=_STRING_USAGE), (11, 7, 18)),
            (_answer(usage={"prompt_tokens": 11.0, "completion_tokens": 7.9, "total_tokens": None}), (11, 7, 18)),
            # A missing total is the sum of the two counts.
            (_answer(usage={"prompt_tokens": 11, "completion_tokens": 7}), (11, 7, 18)),
            (_answer(usage={**_USAGE, "prompt_tokens_details": None, "completion_tokens_details": None}), (11, 7, 18)),
            # A gateway that reports no usage leaves no usage event, and the call still answers.
            (_answer(usage=None), None),
            (_answer(usage={}), None),
            (_answer(usage={"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}), None),
            ({k: v for k, v in _answer().items() if k != "usage"}, None),
        ],
        ids=["plain", "strings", "floats", "no-total", "null-details", "null", "empty", "null-counts", "missing"],
    )
    async def test_usage_is_read_whatever_way_the_gateway_wrote_it(
        self, body: Body, usage: tuple[int, int, int] | None, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = await _invoke(serve_answer, body)

        assert message.content == "hello"
        assert _usage(tracker) == usage

    @pytest.mark.parametrize(
        ("body", "finish"),
        [
            (_answer(finish="stop"), "stop"),
            (_answer(finish=None), "stop"),
            (_answer(finish="end_turn"), "stop"),
            (_answer(finish="STOP"), "stop"),
            (_answer(finish="eos"), "stop"),
            (_answer(finish="something_new"), "stop"),
            (_answer(finish="length"), "length"),
            (_answer(finish="max_tokens"), "length"),
            (_answer(finish="MAX_TOKENS"), "length"),
            (_answer(finish="content_filter"), "content_filter"),
            (_answer(finish="SAFETY"), "content_filter"),
            (_answer(_TOOL_MESSAGE, finish="tool_calls"), "tool_calls"),
            (_answer(_TOOL_MESSAGE, finish="tool_use"), "tool_calls"),
            # A tool call is what ended the answer, whatever word the gateway used for it.
            (_answer(_TOOL_MESSAGE, finish="stop"), "tool_calls"),
            (_answer(_TOOL_MESSAGE, finish=None), "tool_calls"),
        ],
        ids=[
            "stop",
            "null",
            "end_turn",
            "STOP",
            "eos",
            "unknown-word",
            "length",
            "max_tokens",
            "MAX_TOKENS",
            "content_filter",
            "SAFETY",
            "tool_calls",
            "tool_use",
            "stop-with-calls",
            "null-with-calls",
        ],
    )
    async def test_the_finish_reason_is_one_of_openais_five(
        self, body: Body, finish: str, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = await _invoke(serve_answer, body)

        assert message.response_metadata["finish_reason"] == finish
        assert tracker.last_finish_reason == finish

    @pytest.mark.parametrize(
        "message",
        [
            {"role": None},
            {"tool_calls": None},
            {"content": [{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}, {"type": "image"}]},
        ],
        ids=["no-role", "null-tool-calls", "typed-parts"],
    )
    async def test_a_message_is_read_when_a_field_is_null_or_typed_parts(
        self, message: Body, serve_answer: Serve
    ) -> None:
        answer = await _invoke(serve_answer, _answer(message))

        assert answer.content == "hello"
        assert answer.tool_calls == []

    async def test_a_choice_without_an_index_is_read(self, serve_answer: Serve) -> None:
        body = _answer()
        del body["choices"][0]["index"]  # type: ignore[index]

        assert (await _invoke(serve_answer, body)).content == "hello"

    @pytest.mark.parametrize(
        "body",
        [
            _answer(choices=[{"index": 0, "finish_reason": "stop"}]),
            _answer(choices=None),
            _answer(choices=[]),
            _answer(choices=["nope"]),
            {"id": "x", "choices": None, "base_resp": {"status_code": 0, "status_msg": "ok"}},
        ],
        ids=["no-message", "null-choices", "no-choices", "not-a-choice", "success-base-resp"],
    )
    async def test_an_answer_without_a_readable_choice_is_the_providers_fault_and_repeated(
        self, body: Body, serve_answer: Serve
    ) -> None:
        with pytest.raises(LLMResponseError, match="answered") as caught:
            await _invoke(serve_answer, body)

        assert classify_error(caught.value) == ErrorKind.OVERLOADED

    @pytest.mark.parametrize(
        ("body", "kind"),
        [
            ({"error": {"message": "Rate limit reached", "type": "rate_limit_exceeded"}}, ErrorKind.RATE_LIMIT),
            ({"error": {"message": "The server had an error", "type": "server_error"}}, ErrorKind.OVERLOADED),
            ({"error": {"message": "Something went wrong"}}, ErrorKind.UNKNOWN),
            (_answer(error={"message": "partial", "code": 500}), ErrorKind.OVERLOADED),
            # MiniMax answers a failure with 200, no choices and its own code.
            ({"choices": None, "base_resp": {"status_code": 1002, "status_msg": "rate limited"}}, ErrorKind.RATE_LIMIT),
            ({"choices": None, "base_resp": {"status_code": 1004, "status_msg": "login fail"}}, ErrorKind.AUTH),
            ({"choices": None, "base_resp": {"status_code": 9999, "status_msg": "?"}}, ErrorKind.OVERLOADED),
            (_failed_choice({"code": 502, "message": "Provider returned error"}), ErrorKind.OVERLOADED),
            (_answer({"content": "part"}, finish="ERROR"), ErrorKind.UNKNOWN),
            # DeepSeek interrupts a request when its inference system runs short; what came is a part of the answer.
            (_answer({"content": "part"}, finish="insufficient_system_resource"), ErrorKind.OVERLOADED),
            (_answer({"content": "part"}, finish="aborted"), ErrorKind.OVERLOADED),
        ],
        ids=[
            "rate-limit",
            "server-error",
            "bare",
            "error-with-choices",
            "base-resp-1002",
            "base-resp-1004",
            "base-resp-unlisted",
            "failed-choice",
            "error-finish-no-detail",
            "deepseek-no-resource",
            "deepseek-aborted",
        ],
    )
    async def test_a_failure_sent_with_a_200_status_raises_and_is_classified(
        self, body: Body, kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            await _invoke(serve_answer, body)

        assert classify_error(caught.value) == kind

    @pytest.mark.parametrize("error", [None, "", {}, False, 0], ids=["null", "text", "object", "false", "zero"])
    async def test_an_empty_error_field_is_not_a_failure(self, error: object, serve_answer: Serve) -> None:
        assert (await _invoke(serve_answer, _answer(error=error))).content == "hello"


class TestStreamedAnswers:
    @pytest.mark.parametrize(
        ("tail", "usage"),
        [
            ([_chunk({}, "stop", usage=dict(_USAGE))], (11, 7, 18)),
            ([_chunk({}, "stop"), _usage_only(dict(_USAGE))], (11, 7, 18)),
            ([_chunk({}, "stop"), {"id": "c1", "choices": None, "usage": dict(_USAGE)}], (11, 7, 18)),
            ([_chunk({}, "stop"), {"id": "c1", "usage": dict(_USAGE)}], (11, 7, 18)),
            ([_chunk({}, "stop"), _usage_only(_STRING_USAGE)], (11, 7, 18)),
            ([_chunk({}, "stop"), _usage_only({**_USAGE, "prompt_tokens_details": None})], (11, 7, 18)),
            ([_chunk({}, "stop"), _usage_only(None, error=None)], None),
        ],
        ids=["on-the-finish-chunk", "own-chunk", "null-choices", "no-choices-key", "strings", "null-details", "null"],
    )
    async def test_usage_is_read_from_whichever_chunk_carries_it(
        self, tail: list[Body], usage: tuple[int, int, int] | None, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = await _stream_all(serve_answer, _chunk({"content": "hello"}), *tail)

        assert message.content == "hello"
        assert _usage(tracker) == usage

    @pytest.mark.parametrize(
        ("word", "finish"),
        [
            ("stop", "stop"),
            ("end_turn", "stop"),
            ("STOP", "stop"),
            ("eos", "stop"),
            ("something_new", "stop"),
            ("length", "length"),
            ("max_tokens", "length"),
            ("MAX_TOKENS", "length"),
            ("content_filter", "content_filter"),
            ("SAFETY", "content_filter"),
            ("tool_calls", "tool_calls"),
            ("tool_use", "tool_calls"),
        ],
    )
    async def test_the_finish_reason_is_one_of_openais_five(
        self, word: str, finish: str, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        await _stream_all(serve_answer, _chunk({"content": "hello"}), _chunk({}, word))

        assert tracker.last_finish_reason == finish

    @pytest.mark.parametrize(
        "frames",
        [
            [_chunk({"content": "hello"}, error=None), _chunk({}, "stop", error=None)],
            [_chunk({"content": "hello"}), _chunk({}, "stop"), _usage_only(dict(_USAGE), error=None)],
            [
                {"id": "c1", "choices": [{"delta": {"content": "hello"}, "finish_reason": None}]},
                {"id": "c1", "choices": [{"delta": {}, "finish_reason": "stop"}]},
            ],
            [
                _chunk({"content": "hello"}),
                {"id": "c1", "choices": [{"index": 0, "delta": None, "finish_reason": "stop"}]},
            ],
            [{"id": "", "prompt_filter_results": [{"prompt_index": 0}], "choices": []}, _chunk({"content": "hello"})],
            [_chunk({"role": "assistant", "content": ""}), _chunk({"content": None}), _chunk({"content": "hello"})],
            # A frame that carries no payload is not content: a keep-alive word between chunks changes nothing.
            [_chunk({"content": "hel"}), "ping", _chunk({"content": "lo"}), _chunk({}, "stop")],
            [_chunk({"content": "hel"}), "[PING]", _chunk({"content": "lo"}), _chunk({}, "stop")],
        ],
        ids=[
            "null-error",
            "null-error-last",
            "no-index",
            "null-delta",
            "prompt-filter",
            "null-content",
            "keep-alive-word",
            "bracketed-marker",
        ],
    )
    async def test_a_chunk_that_is_odd_but_not_a_failure_is_read(
        self, frames: list[Body | str], serve_answer: Serve
    ) -> None:
        assert (await _stream_all(serve_answer, *frames)).content == "hello"

    async def test_tool_calls_survive_a_finish_word_of_another_vendor(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        call = {"index": 0, **_CALL}
        message = await _stream_all(
            serve_answer, _chunk({"role": "assistant", "tool_calls": [call]}), _chunk({}, "tool_use")
        )

        assert [(c["name"], c["args"]) for c in message.tool_calls] == [("get_weather", {"city": "Tokyo"})]
        assert tracker.last_finish_reason == "tool_calls"

    @pytest.mark.parametrize(
        ("frames", "kind"),
        [
            # OpenRouter: the upstream failed mid-answer, and the chunk says so next to the choices.
            (
                [_chunk({"content": "hel"}), _chunk({"content": ""}, "error", error={"code": 502, "message": "cut"})],
                ErrorKind.OVERLOADED,
            ),
            (
                [_chunk({"content": "hel"}), _usage_only(None, error={"message": "boom", "code": 500})],
                ErrorKind.OVERLOADED,
            ),
            (
                [
                    _chunk({"content": "hel"}),
                    {"error": {"message": "Rate limit reached", "type": "rate_limit_exceeded"}},
                ],
                ErrorKind.RATE_LIMIT,
            ),
            ([_chunk({"content": "hel"}), _chunk({}, "error")], ErrorKind.OVERLOADED),
            ([_chunk({"content": "hel"}), _chunk({}, "insufficient_system_resource")], ErrorKind.OVERLOADED),
            ([_chunk({"content": "hel"}), _chunk({}, "aborted")], ErrorKind.OVERLOADED),
            # A payload cut or corrupted on the way is not skipped: the answer would silently miss what it carried.
            (
                [_chunk({"content": "hel"}), '{"id": "c1", "choices": [{"index": 0, "delta": {"con'],
                ErrorKind.OVERLOADED,
            ),
        ],
        ids=[
            "error-with-choices",
            "error-only",
            "rate-limit",
            "error-finish",
            "deepseek-no-resource",
            "deepseek-aborted",
            "corrupted-frame",
        ],
    )
    async def test_a_failure_in_the_middle_of_the_answer_raises_instead_of_ending_it(
        self, frames: list[Body | str], kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            await _stream_all(serve_answer, *frames)

        assert classify_error(caught.value) == kind
