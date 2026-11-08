"""Tests for Responses wire invocation error propagation."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import (
    invoke_responses_sync,
    stream_responses_sync,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import ResponsesStreamError


def _input_types(call: dict[str, object]) -> list[str]:
    """The item types of the ``input`` a recorded ``responses`` call carried."""
    items = call["input"]
    assert isinstance(items, list)
    return [str(item["type"]) for item in items if isinstance(item, dict) and "type" in item]


class _FakeResponsesStream:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = events

    def __iter__(self):
        return iter(self._events)


class _StreamResponsesClient:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = events

    def responses(self, **_kwargs: object) -> _FakeResponsesStream:
        return _FakeResponsesStream(self._events)


class _FailOpenInvokeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def responses(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append(dict(_kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("invalid_encrypted_content: stale blob")
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ]
        }


def test_invoke_responses_sync_fail_open_on_invalid_encrypted_content() -> None:
    client = _FailOpenInvokeClient()
    messages = [
        {
            "role": "assistant",
            "content": "prior",
            "responses_reasoning_items": [{"type": "reasoning", "encrypted_content": "stale"}],
        }
    ]
    params = {"extra_body": {"include": ["reasoning.encrypted_content"]}}
    result = invoke_responses_sync(client, messages, params)
    assert len(client.calls) == 2
    assert "include" in client.calls[0]
    assert "include" not in client.calls[1]
    assert "reasoning" in _input_types(client.calls[0])
    assert "reasoning" not in _input_types(client.calls[1])
    assert [call["stream"] for call in client.calls] == [False, False]
    assert result["choices"][0]["message"]["content"] == "ok"


_CHAT_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file",
        "parameters": {"type": "object"},
        "strict": True,
        "title": "not part of the Responses shape",
    },
}
_RESPONSES_TOOL = {
    "type": "function",
    "name": "read_file",
    "description": "Read a file",
    "parameters": {"type": "object"},
    "strict": True,
}


def test_tools_reach_the_responses_wire_in_its_own_shape() -> None:
    client = _FailOpenInvokeClient()
    nameless = {"type": "function", "function": {"description": "no name to flatten"}}
    hosted = {"type": "web_search"}
    invoke_responses_sync(client, [{"role": "user", "content": "hi"}], {"tools": [_CHAT_TOOL, hosted, nameless]})
    # A tool the wire cannot flatten is passed on untouched; the retry sends the same tools as the first call.
    assert client.calls[0]["tools"] == [_RESPONSES_TOOL, hosted, nameless]
    assert client.calls[1]["tools"] == client.calls[0]["tools"]


def test_stream_responses_sync_raises_on_failed_event() -> None:
    client = _StreamResponsesClient(
        [{"type": "response.failed", "error": {"message": "Training not allowed for contributor"}}],
    )
    with pytest.raises(ResponsesStreamError, match="Training not allowed"):
        list(stream_responses_sync(client, [], {}))


def test_stream_responses_sync_yields_normal_chunks() -> None:
    client = _StreamResponsesClient(
        [{"type": "response.output_text.delta", "delta": "hi"}],
    )
    chunks = list(stream_responses_sync(client, [], {}))
    assert len(chunks) == 1
    assert chunks[0]["choices"][0]["delta"]["content"] == "hi"


class _FailOpenStreamClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def responses(self, **_kwargs: object) -> _FakeResponsesStream:
        self.calls.append(dict(_kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("invalid_encrypted_content: stale blob")
        return _FakeResponsesStream([{"type": "response.output_text.delta", "delta": "retry-ok"}])


def test_stream_responses_sync_fail_open_on_invalid_encrypted_content() -> None:
    client = _FailOpenStreamClient()
    messages = [
        {
            "role": "assistant",
            "content": "prior",
            "responses_reasoning_items": [{"type": "reasoning", "encrypted_content": "stale"}],
        }
    ]
    params = {"extra_body": {"include": ["reasoning.encrypted_content"]}}
    chunks = list(stream_responses_sync(client, messages, params))
    assert len(client.calls) == 2
    assert "include" in client.calls[0]
    assert "include" not in client.calls[1]
    assert "reasoning" in _input_types(client.calls[0])
    assert "reasoning" not in _input_types(client.calls[1])
    assert [call["stream"] for call in client.calls] == [True, True]
    assert chunks[0]["choices"][0]["delta"]["content"] == "retry-ok"


class _AsyncFailOpenClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def aresponses(self, **_kwargs: object) -> dict[str, object]:
        self.calls.append(dict(_kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("invalid_encrypted_content: stale blob")
        return {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "async-ok"}],
                }
            ]
        }


@pytest.mark.asyncio
async def test_invoke_responses_async_fail_open_on_invalid_encrypted_content() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import invoke_responses_async

    client = _AsyncFailOpenClient()
    messages = [
        {
            "role": "assistant",
            "content": "prior",
            "responses_reasoning_items": [{"type": "reasoning", "encrypted_content": "stale"}],
        }
    ]
    params = {"extra_body": {"include": ["reasoning.encrypted_content"]}}
    result = await invoke_responses_async(client, messages, params)
    assert len(client.calls) == 2
    assert "include" in client.calls[0]
    assert "include" not in client.calls[1]
    assert "reasoning" in _input_types(client.calls[0])
    assert "reasoning" not in _input_types(client.calls[1])
    assert [call["stream"] for call in client.calls] == [False, False]
    assert result["choices"][0]["message"]["content"] == "async-ok"


class _AsyncStreamClient:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def aresponses(self, **_kwargs: object) -> _AsyncEventStream:
        return _AsyncEventStream(self._events)


class _AsyncEventStream:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def __aiter__(self) -> _AsyncEventStream:
        return self

    async def __anext__(self) -> object:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


@pytest.mark.asyncio
async def test_stream_responses_async_yields_chunks() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import stream_responses_async

    client = _AsyncStreamClient([{"type": "response.output_text.delta", "delta": "async-stream"}])
    chunks = [chunk async for chunk in stream_responses_async(client, [], {})]
    assert len(chunks) == 1
    assert chunks[0]["choices"][0]["delta"]["content"] == "async-stream"


class _BrokenClient:
    """Every call fails with an error that has nothing to do with the reasoning replay."""

    def __init__(self) -> None:
        self.calls = 0

    def responses(self, **_kwargs: object) -> dict[str, object]:
        self.calls += 1
        raise RuntimeError("network down")

    async def aresponses(self, **_kwargs: object) -> dict[str, object]:
        self.calls += 1
        raise RuntimeError("network down")


@pytest.mark.parametrize(
    "run",
    [
        lambda client: invoke_responses_sync(client, [], {}),
        lambda client: list(stream_responses_sync(client, [], {})),
    ],
    ids=["invoke", "stream"],
)
def test_an_unrelated_error_is_raised_at_once_not_retried(run) -> None:
    client = _BrokenClient()
    with pytest.raises(RuntimeError, match="network down"):
        run(client)
    assert client.calls == 1


@pytest.mark.asyncio
async def test_an_unrelated_async_error_is_raised_at_once_not_retried() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import invoke_responses_async, stream_responses_async

    client = _BrokenClient()
    with pytest.raises(RuntimeError, match="network down"):
        await invoke_responses_async(client, [], {})
    with pytest.raises(RuntimeError, match="network down"):
        [chunk async for chunk in stream_responses_async(client, [], {})]
    assert client.calls == 2


class _AnswerClient:
    def __init__(self, answer: dict[str, object]) -> None:
        self._answer = answer

    def responses(self, **_kwargs: object) -> dict[str, object]:
        return self._answer

    async def aresponses(self, **_kwargs: object) -> dict[str, object]:
        return self._answer


_FAILED_ANSWER = {"status": "failed", "error": {"message": "Training not allowed for contributor"}}


def test_a_failed_answer_is_an_error_not_an_empty_reply() -> None:
    with pytest.raises(ResponsesStreamError, match="Training not allowed"):
        invoke_responses_sync(_AnswerClient(_FAILED_ANSWER), [], {})


@pytest.mark.asyncio
async def test_a_failed_async_answer_is_an_error_not_an_empty_reply() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import invoke_responses_async

    with pytest.raises(ResponsesStreamError, match="Training not allowed"):
        await invoke_responses_async(_AnswerClient(_FAILED_ANSWER), [], {})


@pytest.mark.asyncio
async def test_stream_responses_async_raises_on_failed_event() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import stream_responses_async

    client = _AsyncStreamClient([{"type": "response.failed", "error": {"message": "Training not allowed"}}])
    with pytest.raises(ResponsesStreamError, match="Training not allowed"):
        [chunk async for chunk in stream_responses_async(client, [], {})]


class _AsyncFailOpenStreamClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def aresponses(self, **_kwargs: object) -> _AsyncEventStream:
        self.calls.append(dict(_kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("invalid_encrypted_content: stale blob")
        return _AsyncEventStream([{"type": "response.output_text.delta", "delta": "async-retry"}])


@pytest.mark.asyncio
async def test_stream_responses_async_fail_open_on_invalid_encrypted_content() -> None:
    from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import stream_responses_async

    client = _AsyncFailOpenStreamClient()
    messages = [
        {
            "role": "assistant",
            "content": "prior",
            "responses_reasoning_items": [{"type": "reasoning", "encrypted_content": "stale"}],
        },
        {"role": "user", "content": "hi"},
    ]
    params = {"extra_body": {"include": ["reasoning.encrypted_content"]}}
    chunks = [chunk async for chunk in stream_responses_async(client, messages, params)]
    assert len(client.calls) == 2
    assert "include" in client.calls[0]
    assert "include" not in client.calls[1]
    assert "reasoning" in _input_types(client.calls[0])
    assert "reasoning" not in _input_types(client.calls[1])
    assert [call["stream"] for call in client.calls] == [True, True]
    assert chunks[0]["choices"][0]["delta"]["content"] == "async-retry"
