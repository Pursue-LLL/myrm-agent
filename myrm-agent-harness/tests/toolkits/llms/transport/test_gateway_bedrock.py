"""A Bedrock call through the whole path: model factory, adapter, transport, Converse wire, answer decoding, accounting.

The wire tests read requests and answers one function at a time; these replay real ``converse`` bodies and AWS event
streams through ``invoke``/``ainvoke``/``stream``/``astream`` against a provider double, as the agent calls them, and
hold the parts the adapter owns to what Bedrock says: usage and finish reason in the accounting, tool calls under the
name the agent registered, failures classified, a rejected output limit recovered, repeated requests answered once.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from myrm_agent_harness.toolkits.llms.adapters.chat_model import output_cap_recovery
from myrm_agent_harness.toolkits.llms.core.llm import TransportChatModel, create_chat_model
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport import http
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError, LLMHTTPError
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker
from myrm_agent_harness.utils.token_economics.usage_ledger import DROPPED_STREAM_FINISH_REASON

from .event_stream_bodies import (
    CONTENT_TYPE,
    closing,
    converse_answer,
    delta,
    event,
    exception,
    stop,
    text_stream,
    tool_start,
)
from .gateway_bodies import usage_of
from .provider_double import Provider

MODEL = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
BASE = "http://bedrock.test"
Serve = Callable[[bytes, str], None]
WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Weather of a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
}
SEARCH = {"type": "function", "function": {"name": "web.search", "parameters": {"type": "object"}}}
HI = [HumanMessage(content="hi")]


@pytest.fixture(autouse=True)
def _isolated_ceiling_memo() -> Iterator[None]:
    saved = dict(output_cap_recovery._LEARNED_CEILINGS)
    output_cap_recovery._LEARNED_CEILINGS.clear()
    yield
    output_cap_recovery._LEARNED_CEILINGS.clear()
    output_cap_recovery._LEARNED_CEILINGS.update(saved)


@pytest.fixture
def pauses(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The retry loop's waits, recorded instead of slept."""
    waited: list[float] = []

    async def apause(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(http, "_pause", waited.append)
    monkeypatch.setattr(http, "_apause", apause)
    return waited


def _llm(*, streaming: bool, **kwargs: object) -> TransportChatModel:
    return create_chat_model(model=MODEL, base_url=BASE, api_key="k", streaming=streaming, **kwargs)  # type: ignore[arg-type]


def _stream_all(llm: object) -> AIMessageChunk:
    message: AIMessageChunk | None = None
    for part in llm.stream(HI):  # type: ignore[attr-defined]
        message = part if message is None else message + part
    assert message is not None
    return message


def _frames(*messages: bytes) -> bytes:
    return b"".join(messages)


def _converse(*blocks: dict[str, object], **fields: object) -> bytes:
    return json.dumps(converse_answer(*blocks, **fields)).encode()  # type: ignore[arg-type]


def _tool_stream(name: str = "get_weather", reason: str = "tool_use") -> bytes:
    return _frames(
        event("messageStart", {"role": "assistant"}),
        tool_start(0, "tool-1", name),
        delta(0, toolUse={"input": '{"city": "To'}),
        delta(0, toolUse={"input": 'kyo"}'}),
        stop(0),
        *closing(reason),
    )


class TestWholeAnswers:
    def test_text_usage_and_finish_reach_the_message_and_the_accounting(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        serve_answer(
            _converse({"text": "hello"}, usage={"inputTokens": 11, "outputTokens": 7, "totalTokens": 18}),
            "application/json",
        )

        message = _llm(streaming=False).invoke(HI)

        assert message.content == "hello"
        assert usage_of(tracker) == (11, 7, 18)
        assert tracker.last_finish_reason == "stop"

    def test_cache_reads_and_writes_count_toward_the_prompt_the_way_other_providers_report_them(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        usage = {"inputTokens": 11, "outputTokens": 7, "cacheReadInputTokens": 5, "cacheWriteInputTokens": 3}
        serve_answer(_converse({"text": "hello"}, usage=usage), "application/json")

        _llm(streaming=False).invoke(HI)

        assert usage_of(tracker) == (19, 7, 26)

    def test_a_tool_call_comes_back_under_the_name_the_agent_registered(
        self, provider: Provider, tracker: TokenTracker
    ) -> None:
        call = {"toolUse": {"toolUseId": "t1", "name": "x__web_2e_search", "input": {"q": "tokyo"}}}
        provider.serves(
            httpx.Response(
                200, content=_converse(call, reason="tool_use"), headers={"content-type": "application/json"}
            )
        )

        message = _llm(streaming=False).bind_tools([SEARCH]).invoke(HI)

        assert isinstance(message, AIMessage)
        assert [(c["name"], c["args"], c["id"]) for c in message.tool_calls] == [("web.search", {"q": "tokyo"}, "t1")]
        assert tracker.last_finish_reason == "tool_calls"
        sent = json.loads(provider.requests[0].content)
        assert sent["toolConfig"]["tools"][0]["toolSpec"]["name"] == "x__web_2e_search"

    @pytest.mark.asyncio
    async def test_the_async_path_reads_the_same_answer(self, serve_answer: Serve, tracker: TokenTracker) -> None:
        serve_answer(
            _converse({"text": "hello"}, usage={"inputTokens": 11, "outputTokens": 7, "totalTokens": 18}),
            "application/json",
        )

        message = await _llm(streaming=False).ainvoke(HI)

        assert (message.content, usage_of(tracker)) == ("hello", (11, 7, 18))


class TestStreamedAnswers:
    def test_text_pieces_usage_and_finish_are_assembled(self, serve_answer: Serve, tracker: TokenTracker) -> None:
        serve_answer(_frames(*text_stream("hel", "lo")), CONTENT_TYPE)

        message = _stream_all(_llm(streaming=True))

        assert message.content == "hello"
        assert usage_of(tracker) == (9, 5, 14)
        assert tracker.last_finish_reason == "stop"

    def test_a_tool_call_arrives_whole_from_its_argument_pieces(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        serve_answer(_tool_stream(), CONTENT_TYPE)

        message = _stream_all(_llm(streaming=True).bind_tools([WEATHER]))

        assert [(c["name"], c["args"], c["id"]) for c in message.tool_calls] == [
            ("get_weather", {"city": "Tokyo"}, "tool-1")
        ]
        assert tracker.last_finish_reason == "tool_calls"

    def test_a_tool_that_takes_no_arguments_is_called_with_an_empty_object(self, serve_answer: Serve) -> None:
        body = _frames(
            event("messageStart", {"role": "assistant"}), tool_start(0, "t0", "get_time"), stop(0), *closing("tool_use")
        )
        serve_answer(body, CONTENT_TYPE)

        message = _stream_all(_llm(streaming=True))

        assert [(c["name"], c["args"]) for c in message.tool_calls] == [("get_time", {})]

    def test_two_tool_calls_keep_their_own_arguments(self, serve_answer: Serve) -> None:
        body = _frames(
            event("messageStart", {"role": "assistant"}),
            tool_start(0, "a", "get_weather"),
            delta(0, toolUse={"input": '{"city": "Tokyo"}'}),
            stop(0),
            tool_start(1, "b", "get_weather"),
            delta(1, toolUse={"input": '{"city": "Osaka"}'}),
            stop(1),
            *closing("tool_use"),
        )
        serve_answer(body, CONTENT_TYPE)

        message = _stream_all(_llm(streaming=True))

        assert [(c["id"], c["args"]) for c in message.tool_calls] == [
            ("a", {"city": "Tokyo"}),
            ("b", {"city": "Osaka"}),
        ]

    def test_reasoning_streams_apart_from_the_answer(self, serve_answer: Serve) -> None:
        body = _frames(
            event("messageStart", {"role": "assistant"}),
            delta(0, reasoningContent={"text": "think"}),
            delta(0, reasoningContent={"signature": "sig"}),
            stop(0),
            delta(1, text="answer"),
            stop(1),
            *closing(),
        )
        serve_answer(body, CONTENT_TYPE)

        message = _stream_all(_llm(streaming=True))

        assert (message.content, message.additional_kwargs.get("reasoning_content")) == ("answer", "think")

    @pytest.mark.asyncio
    async def test_the_async_stream_reads_the_same_events(self, serve_answer: Serve, tracker: TokenTracker) -> None:
        serve_answer(_frames(*text_stream("hel", "lo")), CONTENT_TYPE)

        message: AIMessageChunk | None = None
        async for part in _llm(streaming=True).astream(HI):
            message = part if message is None else message + part

        assert message is not None
        assert (message.content, usage_of(tracker)) == ("hello", (9, 5, 14))

    def test_an_exception_event_inside_the_stream_fails_the_call_with_the_status_it_stands_for(
        self, serve_answer: Serve
    ) -> None:
        serve_answer(
            _frames(*text_stream("hel")[:2], exception("modelStreamErrorException", "stream broke")), CONTENT_TYPE
        )

        with pytest.raises(LLMAnswerError) as caught:
            _stream_all(_llm(streaming=True))

        assert "stream broke" in str(caught.value)
        assert classify_error(caught.value) == ErrorKind.OVERLOADED

    def test_a_stream_that_ends_without_saying_why_is_recorded_as_dropped(
        self, serve_answer: Serve, tracker: TokenTracker
    ) -> None:
        serve_answer(
            _frames(event("messageStart", {"role": "assistant"}), delta(0, text="partial"), stop(0)), CONTENT_TYPE
        )

        message = _stream_all(_llm(streaming=True))

        assert message.content == "partial"
        assert tracker.last_finish_reason == DROPPED_STREAM_FINISH_REASON


class TestWhatReachesBedrock:
    def test_the_request_is_a_bearer_authenticated_converse_stream_post_with_the_agents_settings(
        self, provider: Provider
    ) -> None:
        provider.serves(
            httpx.Response(200, content=_frames(*text_stream("ok")), headers={"content-type": CONTENT_TYPE})
        )

        llm = _llm(streaming=True, temperature=0.3, max_tokens=512)
        _stream_all(llm.bind_tools([WEATHER], tool_choice="auto", parallel_tool_calls=False))

        request = provider.requests[0]
        assert request.method == "POST"
        assert request.url.raw_path.decode() == "/model/us.anthropic.claude-sonnet-4-5-20250929-v1%3A0/converse-stream"
        assert request.headers["authorization"] == "Bearer k"
        body = json.loads(request.content)
        assert body["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
        assert body["inferenceConfig"] == {"maxTokens": 512, "temperature": 0.3}
        assert body["toolConfig"]["toolChoice"] == {"auto": {}}
        assert body["additionalModelRequestFields"] == {"tool_choice": {"disable_parallel_tool_use": True}}

    def test_a_whole_answer_call_uses_the_converse_operation(self, provider: Provider) -> None:
        provider.serves(
            httpx.Response(200, content=_converse({"text": "hello"}), headers={"content-type": "application/json"})
        )

        _llm(streaming=False).invoke(HI)

        assert provider.requests[0].url.raw_path.decode().endswith("/converse")


class TestFailures:
    @pytest.mark.parametrize("path", ["invoke", "stream"])
    def test_throttling_is_retried_twice_then_read_as_a_rate_limit(
        self, path: str, provider: Provider, pauses: list[float]
    ) -> None:
        throttled = httpx.Response(
            429, json={"message": "Too many requests, please wait"}, headers={"x-amzn-errortype": "ThrottlingException"}
        )
        provider.serves(throttled)
        llm = _llm(streaming=path == "stream")

        with pytest.raises(LLMHTTPError) as caught:
            llm.invoke(HI) if path == "invoke" else _stream_all(llm)

        assert len(provider.requests) == DEFAULT_RETRIES + 1
        assert len(pauses) == DEFAULT_RETRIES
        assert classify_error(caught.value) == ErrorKind.RATE_LIMIT

    def test_a_bad_key_is_not_retried_and_reads_as_an_auth_failure(
        self, provider: Provider, pauses: list[float]
    ) -> None:
        provider.serves(httpx.Response(403, json={"message": "The security token included in the request is invalid."}))

        with pytest.raises(LLMHTTPError) as caught:
            _llm(streaming=False).invoke(HI)

        assert (len(provider.requests), pauses) == (1, [])
        assert classify_error(caught.value) == ErrorKind.AUTH

    def test_a_context_that_is_too_long_reads_as_an_overflow(self, provider: Provider, pauses: list[float]) -> None:
        provider.serves(httpx.Response(400, json={"message": "Input is too long for requested model."}))

        with pytest.raises(LLMHTTPError) as caught:
            _llm(streaming=False).invoke(HI)

        assert len(provider.requests) == 1
        assert classify_error(caught.value) == ErrorKind.CONTEXT_OVERFLOW

    @pytest.mark.parametrize("streaming", [False, True])
    def test_an_output_limit_bedrock_refuses_is_lowered_to_the_one_it_states(
        self, streaming: bool, provider: Provider
    ) -> None:
        refusal = httpx.Response(
            400,
            json={
                "message": "The maximum tokens you requested exceeds the model limit of 8192. "
                "Try again with a maximum tokens value that is lower than 8192."
            },
            headers={"x-amzn-errortype": "ValidationException"},
        )
        answered = httpx.Response(
            200,
            content=_frames(*text_stream("fine")) if streaming else _converse({"text": "fine"}),
            headers={"content-type": CONTENT_TYPE if streaming else "application/json"},
        )
        replies = iter([refusal, answered])
        provider.handler = lambda request: next(replies)
        llm = _llm(streaming=streaming, max_tokens=20000)

        message = _stream_all(llm) if streaming else llm.invoke(HI)

        assert message.content == "fine"
        limits = [json.loads(r.content)["inferenceConfig"]["maxTokens"] for r in provider.requests]
        assert limits == [20000, 8192]


class TestRepeatedRequests:
    """A request Bedrock has already answered is put to Bedrock again: the transport keeps no answers."""

    def test_an_identical_whole_answer_request_reaches_bedrock_each_time(self, provider: Provider) -> None:
        provider.serves(
            httpx.Response(200, content=_converse({"text": "hello"}), headers={"content-type": "application/json"})
        )

        first = _llm(streaming=False).invoke(HI)
        second = _llm(streaming=False).invoke(HI)

        assert (first.content, second.content, len(provider.requests)) == ("hello", "hello", 2)

    def test_an_identical_streamed_request_reaches_bedrock_each_time_and_counts_its_usage_each_time(
        self, provider: Provider, tracker: TokenTracker
    ) -> None:
        provider.serves(
            httpx.Response(200, content=_frames(*text_stream("hel", "lo")), headers={"content-type": CONTENT_TYPE})
        )

        first = _stream_all(_llm(streaming=True))
        second = _stream_all(_llm(streaming=True))

        assert (first.content, second.content, len(provider.requests)) == ("hello", "hello", 2)
        assert tracker.call_count == 2

    def test_a_streamed_tool_call_answer_is_asked_again(self, provider: Provider) -> None:
        provider.serves(httpx.Response(200, content=_tool_stream(), headers={"content-type": CONTENT_TYPE}))

        first = _stream_all(_llm(streaming=True).bind_tools([WEATHER]))
        second = _stream_all(_llm(streaming=True).bind_tools([WEATHER]))

        assert (first.tool_calls[0]["args"], second.tool_calls[0]["args"], len(provider.requests)) == (
            {"city": "Tokyo"},
            {"city": "Tokyo"},
            2,
        )

    def test_a_stream_cut_by_an_exception_is_asked_again(self, provider: Provider) -> None:
        broken = httpx.Response(
            200,
            content=_frames(*text_stream("a")[:2], exception("modelStreamErrorException", "x")),
            headers={"content-type": CONTENT_TYPE},
        )
        provider.serves(broken)
        for _ in range(2):
            with pytest.raises(LLMAnswerError):
                _stream_all(_llm(streaming=True))
        assert len(provider.requests) == 2
