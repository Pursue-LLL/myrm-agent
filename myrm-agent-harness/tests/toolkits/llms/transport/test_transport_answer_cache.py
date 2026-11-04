"""The answer cache on the chat call path: transport and adapter against a provider double that counts its requests."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.toolkits.llms.transport import answer_cache as cache_module
from myrm_agent_harness.toolkits.llms.transport.answer_cache import AnswerCache, answer_cache
from myrm_agent_harness.toolkits.llms.transport.client import get_transport
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker

from .gateway_bodies import answer, chat_model, chunk
from .provider_double import BASE, Provider, adrain, drain, json_response, sse_response

pytestmark = pytest.mark.usefixtures("cache_on")


def _params(**changes: object) -> dict[str, object]:
    return {
        "model": "openai/gpt-4o-mini",
        "api_base": BASE,
        "api_key": "k",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": "hi"}],
        **changes,
    }


def _hello_stream() -> httpx.Response:
    return sse_response(
        chunk({"role": "assistant", "content": "hel"}),
        chunk({"content": "lo"}),
        chunk({}, finish="stop"),
        {"id": "c1", "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
    )


class TestChatAnswers:
    def test_an_identical_request_reaches_the_provider_once(self, provider: Provider) -> None:
        provider.serves(json_response(answer()))

        first = get_transport().completion(**_params())
        second = get_transport().completion(**_params())

        assert (first, second, len(provider.requests)) == (first, first, 1)

    def test_the_async_path_shares_the_cache(self, provider: Provider) -> None:
        provider.serves(json_response(answer()))

        async def ask() -> object:
            return await get_transport().acompletion(**_params())

        first = asyncio.run(ask())
        second = get_transport().completion(**_params())  # the sync path reads what the async path stored

        assert (first, len(provider.requests)) == (second, 1)

    @pytest.mark.parametrize(
        "change",
        [
            {"temperature": 0.7},
            {"model": "openai/gpt-4o"},
            {"messages": [{"role": "user", "content": "hello"}]},
            {"api_base": "http://other-gateway.test/v1"},
            {"api_key": "another-key"},
            {"max_tokens": 77},
        ],
        ids=["temperature", "model", "messages", "endpoint", "credential", "max_tokens"],
    )
    def test_a_request_that_differs_on_the_wire_reaches_the_provider_again(
        self, change: dict[str, object], provider: Provider
    ) -> None:
        provider.serves(json_response(answer()))

        get_transport().completion(**_params())
        get_transport().completion(**_params(**change))

        assert len(provider.requests) == 2

    def test_a_refused_request_is_not_cached(self, provider: Provider) -> None:
        provider.serves(httpx.Response(400, json={"error": {"message": "bad request"}}))
        with pytest.raises(Exception, match="bad request"):
            get_transport().completion(**_params())

        provider.serves(json_response(answer()))
        get_transport().completion(**_params())
        get_transport().completion(**_params())

        assert len(provider.requests) == 2

    @pytest.mark.parametrize("finish", ["length", "content_filter"], ids=["truncated", "filtered"])
    def test_an_answer_that_did_not_finish_normally_is_asked_again(self, finish: str, provider: Provider) -> None:
        provider.serves(json_response(answer(finish=finish)))

        get_transport().completion(**_params())
        get_transport().completion(**_params())

        assert len(provider.requests) == 2

    def test_an_async_answer_that_did_not_finish_normally_is_asked_again(self, provider: Provider) -> None:
        provider.serves(json_response(answer(finish="length")))

        async def ask_twice() -> None:
            await get_transport().acompletion(**_params())
            await get_transport().acompletion(**_params())

        asyncio.run(ask_twice())

        assert len(provider.requests) == 2

    def test_an_empty_answer_is_asked_again(self, provider: Provider) -> None:
        provider.serves(json_response(answer({"content": ""})))

        get_transport().completion(**_params())
        get_transport().completion(**_params())

        assert len(provider.requests) == 2

    def test_an_answer_is_forgotten_after_an_hour(self, provider: Provider, monkeypatch: pytest.MonkeyPatch) -> None:
        now = [0.0]
        monkeypatch.setattr(cache_module, "answer_cache", AnswerCache(enabled=True, clock=lambda: now[0]))
        provider.serves(json_response(answer()))

        get_transport().completion(**_params())
        now[0] += 3599.0
        get_transport().completion(**_params())
        now[0] += 2.0
        get_transport().completion(**_params())

        assert len(provider.requests) == 2

    def test_a_switched_off_cache_asks_the_provider_every_time(self, provider: Provider) -> None:
        answer_cache.enabled = False
        provider.serves(json_response(answer()))

        get_transport().completion(**_params())
        get_transport().completion(**_params())

        assert len(provider.requests) == 2


class TestChatStreams:
    def test_an_identical_stream_is_replayed_chunk_for_chunk(self, provider: Provider) -> None:
        provider.serves(_hello_stream())

        live = get_transport().completion(**_params(stream=True))
        live_chunks = drain(live)
        replay = get_transport().completion(**_params(stream=True))

        assert (drain(replay), len(provider.requests)) == (live_chunks, 1)
        assert replay.received_finish_reason == live.received_finish_reason == "stop"  # type: ignore[union-attr]

    def test_the_async_stream_is_replayed_too(self, provider: Provider) -> None:
        provider.serves(_hello_stream())

        async def run() -> tuple[list[object], list[object], str | None]:
            live = await get_transport().acompletion(**_params(stream=True))
            live_chunks = await adrain(live)
            replay = await get_transport().acompletion(**_params(stream=True))
            return live_chunks, await adrain(replay), replay.received_finish_reason

        live_chunks, replayed, finish = asyncio.run(run())

        assert (replayed, finish, len(provider.requests)) == (live_chunks, "stop", 1)

    def test_a_stream_and_a_plain_request_do_not_share_an_answer(self, provider: Provider) -> None:
        provider.handler = lambda request: (
            _hello_stream() if json.loads(request.content).get("stream") else json_response(answer())
        )

        get_transport().completion(**_params())
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_stream_the_consumer_gave_up_on_is_asked_again(self, provider: Provider) -> None:
        provider.serves(_hello_stream())

        stream = get_transport().completion(**_params(stream=True))
        next(stream)  # type: ignore[call-overload]
        stream.close()  # type: ignore[union-attr]
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_stream_cut_before_the_provider_finished_it_is_asked_again(self, provider: Provider) -> None:
        provider.serves(sse_response(chunk({"role": "assistant", "content": "half an ans"})))

        drain(get_transport().completion(**_params(stream=True)))
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_stream_that_said_nothing_is_asked_again(self, provider: Provider) -> None:
        provider.serves(sse_response(chunk({"role": "assistant"}), chunk({}, finish="stop")))

        drain(get_transport().completion(**_params(stream=True)))
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_stream_that_ended_on_length_is_asked_again(self, provider: Provider) -> None:
        provider.serves(sse_response(chunk({"content": "cut"}), chunk({}, finish="length")))

        drain(get_transport().completion(**_params(stream=True)))
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_stream_that_outgrows_the_cache_part_way_is_not_kept(
        self, provider: Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cache_module, "MAX_ENTRY_CHARS", 300)
        provider.serves(sse_response(chunk({"content": "a"}), chunk({"content": "x" * 400}), chunk({}, finish="stop")))

        drain(get_transport().completion(**_params(stream=True)))
        drain(get_transport().completion(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_a_replayed_tool_call_arrives_whole(self, provider: Provider) -> None:
        call = {"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}
        provider.serves(
            sse_response(chunk({"role": "assistant", "tool_calls": [call]}), chunk({}, finish="tool_calls"))
        )

        live = drain(get_transport().completion(**_params(stream=True)))
        replayed = drain(get_transport().completion(**_params(stream=True)))

        assert (replayed, len(provider.requests)) == (live, 1)


class TestThroughTheAdapter:
    def test_a_repeated_prompt_costs_one_provider_call_and_reads_the_same(
        self, provider: Provider, tracker: TokenTracker
    ) -> None:
        provider.serves(json_response(answer()))
        model = chat_model(streaming=False)

        first = model.invoke([HumanMessage(content="hi")])
        second = model.invoke([HumanMessage(content="hi")])

        assert (first.content, second.content, len(provider.requests)) == ("hello", "hello", 1)
        assert tracker.call_count == 2  # a replayed answer is accounted like an answered one

    def test_a_repeated_streamed_prompt_reads_the_same_text(self, provider: Provider) -> None:
        provider.serves(_hello_stream())

        async def read() -> str:
            model = chat_model(streaming=True)
            return "".join([str(part.content) async for part in model.astream([HumanMessage(content="hi")])])

        assert (asyncio.run(read()), asyncio.run(read()), len(provider.requests)) == ("hello", "hello", 1)
