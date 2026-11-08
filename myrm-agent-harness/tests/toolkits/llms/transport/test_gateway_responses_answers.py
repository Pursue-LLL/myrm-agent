"""Responses-wire answers replayed through the whole call path (adapter included).

Each case was measured on the stack this one replaced first: the answer that has no usage, the usage that is not
numbers and the failure in the middle of a stream are where the two must behave alike, or better (an ``error`` event
OpenAI documents with ``code`` and ``message`` on the event itself used to end the answer quietly).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import ResponsesStreamError
from myrm_agent_harness.toolkits.llms.core.llm import TransportChatModel, create_chat_model
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker

Body = dict[str, object]
Event = tuple[str, Body]
Serve = Callable[[bytes, str], None]
_FAILURES = (ResponsesStreamError, LLMAnswerError)
_USAGE: Body = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
_MESSAGE: Body = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hello"}]}
_CALL: Body = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_1",
    "name": "get_weather",
    "arguments": '{"city": "Tokyo"}',
}


def _response(**fields: object) -> Body:
    return {
        "id": "resp_1",
        "object": "response",
        "model": "gpt-5",
        "status": "completed",
        "output": [_MESSAGE],
        **fields,
    }


def _delta(text: str) -> Event:
    return "response.output_text.delta", {"type": "response.output_text.delta", "delta": text}


def _done(event: str = "response.completed", **fields: object) -> Event:
    return event, {"type": event, "response": _response(**fields)}


def _model(*, streaming: bool) -> TransportChatModel:
    return create_chat_model(
        model="openai/gpt-5",
        base_url="http://gateway.test/v1",
        api_key="k",
        wire_protocol="responses",
        streaming=streaming,
    )


async def _invoke(serve_answer: Serve, body: Body) -> AIMessage:
    serve_answer(json.dumps(body).encode(), "application/json")
    return await _model(streaming=False).ainvoke([HumanMessage(content="hi")])


async def _stream_all(serve_answer: Serve, *events: Event) -> AIMessageChunk:
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    serve_answer(body.encode(), "text/event-stream")
    message: AIMessageChunk | None = None
    async for part in _model(streaming=True).astream([HumanMessage(content="hi")]):
        message = part if message is None else message + part
    assert message is not None
    return message


def _usage(tracker: TokenTracker) -> tuple[int, int, int] | None:
    if tracker.call_count == 0:
        return None
    usage = tracker.usage
    return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens


class TestNonStreamingAnswers:
    @pytest.mark.parametrize(
        ("usage", "recorded"),
        [
            (_USAGE, (11, 7, 18)),
            ({"input_tokens": "11", "output_tokens": "7"}, (11, 7, 18)),
            ({"input_tokens": 11.0, "output_tokens": 7.9}, (11, 7, 18)),
            ({"prompt_tokens": 11, "completion_tokens": 7}, (11, 7, 18)),
            # An answer that reports no usage still has its call counted, at zero tokens.
            (None, (0, 0, 0)),
            ({}, (0, 0, 0)),
            # Counts that are not numbers are zero, and the answer is still read.
            ({"input_tokens": "n/a", "output_tokens": []}, (0, 0, 0)),
            ({"input_tokens": None, "output_tokens": None}, (0, 0, 0)),
            ({"input_tokens": -5, "output_tokens": 7}, (0, 7, 7)),
        ],
        ids=["plain", "strings", "floats", "chat-names", "null", "empty", "junk", "null-counts", "negative"],
    )
    async def test_usage_is_read_whatever_way_the_provider_wrote_it(
        self, usage: Body | None, recorded: tuple[int, int, int], serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = await _invoke(serve_answer, _response(usage=usage))

        assert message.content == "hello"
        assert _usage(tracker) == recorded

    async def test_an_answer_without_a_usage_field_is_read(self, serve_answer: Serve, tracker: TokenTracker) -> None:
        message = await _invoke(serve_answer, _response())

        assert message.content == "hello"
        assert _usage(tracker) == (0, 0, 0)

    async def test_an_incomplete_answer_ended_by_the_output_cap_says_so(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        body = _response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}, usage=_USAGE)

        await _invoke(serve_answer, body)

        assert tracker.last_finish_reason == "length"

    @pytest.mark.parametrize(
        ("body", "kind"),
        [
            (
                _response(status="failed", output=[], error={"code": "server_error", "message": "boom"}),
                ErrorKind.OVERLOADED,
            ),
            (
                _response(status="failed", output=[], error={"code": "rate_limit_exceeded", "message": "slow"}),
                ErrorKind.RATE_LIMIT,
            ),
            (_response(status="failed", output=[], error={"message": "unnamed"}), ErrorKind.UNKNOWN),
            ({"error": {"message": "bare failure", "type": "server_error"}}, ErrorKind.OVERLOADED),
        ],
        ids=["failed-server-error", "failed-rate-limit", "failed-unnamed", "bare-error-body"],
    )
    async def test_a_failed_answer_raises_and_is_classified(
        self, body: Body, kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            await _invoke(serve_answer, body)

        assert classify_error(caught.value) == kind


class TestStreamedAnswers:
    async def test_the_full_event_sequence_openai_documents_is_read(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        created: Body = {"type": "response.created", "response": _response(status="in_progress", output=[], usage=None)}
        item: Body = {"type": "message", "id": "msg_1", "role": "assistant", "content": []}
        message = await _stream_all(
            serve_answer,
            ("response.created", created),
            ("response.in_progress", {**created, "type": "response.in_progress"}),
            ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item}),
            _delta("hel"),
            _delta("lo"),
            ("response.output_text.done", {"type": "response.output_text.done", "text": "hello"}),
            _done(usage=_USAGE),
        )

        assert message.content == "hello"
        assert _usage(tracker) == (11, 7, 18)
        assert tracker.last_finish_reason == "stop"

    @pytest.mark.parametrize(
        ("usage", "recorded"),
        [
            (_USAGE, (11, 7, 18)),
            ({"input_tokens": "11", "output_tokens": "7"}, (11, 7, 18)),
            # Usage a stream leaves out is counted locally: "hi" is 8 prompt tokens with the reply priming, "hello" one.
            (None, (8, 1, 9)),
            ({"input_tokens": "n/a", "output_tokens": []}, (0, 0, 0)),
        ],
        ids=["plain", "strings", "null", "junk"],
    )
    async def test_usage_is_read_from_the_closing_event(
        self, usage: Body | None, recorded: tuple[int, int, int], serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        message = await _stream_all(serve_answer, _delta("hello"), _done(usage=usage))

        assert message.content == "hello"
        assert _usage(tracker) == recorded

    async def test_an_answer_cut_by_the_output_cap_says_so_and_is_billed(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        await _stream_all(serve_answer, _delta("hel"), _done("response.incomplete", status="incomplete", usage=_USAGE))

        assert tracker.last_finish_reason == "length"
        assert _usage(tracker) == (11, 7, 18)

    async def test_a_tool_call_is_read(self, serve_answer: Serve, tracker: TokenTracker) -> None:
        added: Body = {"type": "response.output_item.done", "output_index": 0, "item": _CALL}
        message = await _stream_all(serve_answer, ("response.output_item.done", added), _done(output=[_CALL]))

        assert [(c["name"], c["args"]) for c in message.tool_calls] == [("get_weather", {"city": "Tokyo"})]
        assert tracker.last_finish_reason == "tool_calls"

    async def test_an_mcp_call_that_failed_does_not_end_the_answer(self, serve_answer: Serve) -> None:
        failed: Body = {"type": "response.mcp_call.failed", "item_id": "mcp_1", "output_index": 1}

        message = await _stream_all(
            serve_answer, _delta("hel"), ("response.mcp_call.failed", failed), _delta("lo"), _done()
        )

        assert message.content == "hello"

    @pytest.mark.parametrize(
        ("event", "kind"),
        [
            # OpenAI's own error event: code and message on the event.
            (
                ("error", {"type": "error", "code": "server_error", "message": "boom", "sequence_number": 2}),
                ErrorKind.OVERLOADED,
            ),
            (
                ("error", {"type": "error", "code": "rate_limit_exceeded", "message": "slow", "sequence_number": 2}),
                ErrorKind.RATE_LIMIT,
            ),
            # The same nested in ``error``, as a gateway writes it.
            (
                ("error", {"type": "error", "error": {"code": "rate_limit_exceeded", "message": "slow"}}),
                ErrorKind.RATE_LIMIT,
            ),
            (("error", {"type": "error", "message": "unnamed fault"}), ErrorKind.OVERLOADED),
            (
                _done("response.failed", status="failed", error={"code": "server_error", "message": "boom"}),
                ErrorKind.OVERLOADED,
            ),
            (("response.failed", {"type": "response.failed"}), ErrorKind.OVERLOADED),
            (("message", {"error": {"message": "untyped fault"}}), ErrorKind.OVERLOADED),
        ],
        ids=[
            "flat-server-error",
            "flat-rate-limit",
            "nested-rate-limit",
            "flat-unnamed",
            "failed",
            "failed-bare",
            "untyped",
        ],
    )
    async def test_a_failure_in_the_middle_of_the_answer_raises_instead_of_ending_it(
        self, event: Event, kind: ErrorKind, serve_answer: Serve
    ) -> None:
        with pytest.raises(_FAILURES) as caught:
            await _stream_all(serve_answer, _delta("hel"), event)

        assert classify_error(caught.value) == kind
