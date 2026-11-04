"""The answer cache: what it keeps, for how long, and what it never replays."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.transport import answer_cache as cache_module
from myrm_agent_harness.toolkits.llms.transport.answer_cache import (
    CHAT,
    RESPONSES,
    AnswerCache,
    AsyncReplayStream,
    ReplayStream,
    acached_answer,
    cached_answer,
    request_key,
)
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest

Answer = dict[str, object]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> Iterator[AnswerCache]:
    """A small cache in place of the process-wide one, on a clock the test moves."""
    fresh = AnswerCache(enabled=True, max_entries=3, ttl_seconds=60.0, max_entry_chars=200, clock=clock)
    monkeypatch.setattr(cache_module, "answer_cache", fresh)
    yield fresh


def _request(**changes: object) -> PreparedRequest:
    fields: dict[str, object] = {
        "provider": "openai",
        "url": "https://api.example.test/v1/chat/completions",
        "headers": {"Authorization": "Bearer k"},
        "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.0},
        "timeout": 30.0,
    }
    return PreparedRequest(**{**fields, **changes})  # type: ignore[arg-type]


class TestStore:
    def test_an_entry_is_served_until_its_time_to_live_is_over(self, cache: AnswerCache, clock: Clock) -> None:
        cache.put("k", '{"a":1}')

        clock.now += 59.0
        assert cache.get("k") == '{"a":1}'

        clock.now += 1.0
        assert cache.get("k") is None
        assert len(cache) == 0

    def test_the_least_recently_used_entry_goes_first_once_the_cache_is_full(self, cache: AnswerCache) -> None:
        for key in ("a", "b", "c"):
            cache.put(key, f'"{key}"')
        assert cache.get("a") == '"a"'  # a hit makes "a" the most recent

        cache.put("d", '"d"')

        assert [cache.get(key) for key in ("a", "b", "c", "d")] == ['"a"', None, '"c"', '"d"']

    def test_an_entry_over_the_size_limit_is_not_kept(self, cache: AnswerCache) -> None:
        cache.put("big", '"' + "x" * 200 + '"')

        assert cache.get("big") is None

    def test_clear_forgets_every_entry(self, cache: AnswerCache) -> None:
        cache.put("k", '"v"')

        cache.clear()

        assert cache.get("k") is None


class TestRequestKey:
    def test_the_same_request_has_the_same_key_whatever_the_order_of_its_fields(self) -> None:
        one = _request(body={"model": "m", "temperature": 0.0})
        two = _request(body={"temperature": 0.0, "model": "m"})

        assert request_key(one) == request_key(two)

    @pytest.mark.parametrize(
        "change",
        [
            {"body": {"model": "m2", "messages": [], "temperature": 0.0}},
            {"url": "https://other.example.test/v1/chat/completions"},
            {"headers": {"Authorization": "Bearer other"}},
            {"query": {"api-version": "1"}},
            {"stream": True},
            {"provider": "azure"},
        ],
        ids=["body", "endpoint", "credential", "query", "stream", "provider"],
    )
    def test_whatever_the_provider_sees_tells_requests_apart(self, change: dict[str, object]) -> None:
        assert request_key(_request(**change)) != request_key(_request())

    def test_what_the_provider_never_sees_does_not(self) -> None:
        assert request_key(_request(timeout=5.0, retries=3, proxy="http://proxy:8080")) == request_key(_request())

    def test_an_upload_has_no_key(self) -> None:
        assert request_key(_request(body=None, form={"prompt": "a cat"})) is None


class TestNonStreamingAnswers:
    def test_an_identical_request_is_answered_from_the_cache(self, cache: AnswerCache) -> None:
        produced: list[int] = []

        def produce() -> Answer:
            produced.append(1)
            return {"n": len(produced)}

        first = cached_answer(_request(), produce)
        second = cached_answer(_request(), produce)

        assert (first, second, len(produced)) == ({"n": 1}, {"n": 1}, 1)

    def test_the_cache_hands_out_a_copy_nobody_can_corrupt(self, cache: AnswerCache) -> None:
        cached_answer(_request(), lambda: {"items": [1]})

        cached_answer(_request(), lambda: {"items": [2]})["items"].append(99)  # type: ignore[attr-defined]

        assert cached_answer(_request(), lambda: {"items": [3]}) == {"items": [1]}

    def test_the_answer_of_the_first_request_is_not_aliased_by_the_cache(self, cache: AnswerCache) -> None:
        first = cached_answer(_request(), lambda: {"items": [1]})
        first["items"].append(99)  # type: ignore[attr-defined]

        assert cached_answer(_request(), lambda: {"items": [3]}) == {"items": [1]}

    def test_an_answer_that_is_not_worth_keeping_is_asked_again(self, cache: AnswerCache) -> None:
        produced: list[int] = []

        def produce() -> Answer:
            produced.append(1)
            return {"ok": False}

        cached_answer(_request(), produce, keep=lambda answer: bool(answer["ok"]))
        cached_answer(_request(), produce, keep=lambda answer: bool(answer["ok"]))

        assert len(produced) == 2

    def test_a_failed_request_leaves_nothing_behind(self, cache: AnswerCache) -> None:
        def fail() -> Answer:
            raise RuntimeError("provider down")

        with pytest.raises(RuntimeError):
            cached_answer(_request(), fail)

        assert cached_answer(_request(), lambda: {"ok": True}) == {"ok": True}

    def test_a_switched_off_cache_neither_serves_nor_keeps(self, cache: AnswerCache) -> None:
        cache.enabled = False
        produced: list[int] = []

        def produce() -> Answer:
            produced.append(1)
            return {"n": len(produced)}

        cached_answer(_request(), produce)
        cached_answer(_request(), produce)

        assert (len(produced), len(cache)) == (2, 0)

    def test_an_upload_is_never_replayed(self, cache: AnswerCache) -> None:
        produced: list[int] = []

        def produce() -> Answer:
            produced.append(1)
            return {"n": 1}

        for _ in range(2):
            cached_answer(_request(body=None, form={"prompt": "a cat"}), produce)

        assert (len(produced), len(cache)) == (2, 0)

    def test_an_answer_that_is_not_plain_json_is_returned_but_not_kept(self, cache: AnswerCache) -> None:
        odd: Answer = {"values": {1, 2}}

        assert cached_answer(_request(), lambda: odd) is odd
        assert len(cache) == 0

    def test_the_async_twin_serves_and_keeps_the_same_way(self, cache: AnswerCache) -> None:
        produced: list[int] = []

        async def produce() -> Answer:
            produced.append(1)
            return {"n": len(produced)}

        async def run() -> tuple[Answer, Answer]:
            return await acached_answer(_request(), produce), await acached_answer(_request(), produce)

        assert (asyncio.run(run()), len(produced)) == (({"n": 1}, {"n": 1}), 1)

    def test_the_async_twin_asks_again_for_an_answer_that_is_not_worth_keeping(self, cache: AnswerCache) -> None:
        produced: list[int] = []

        async def produce() -> Answer:
            produced.append(1)
            return {"ok": False}

        async def run() -> None:
            for _ in range(2):
                await acached_answer(_request(), produce, keep=lambda answer: bool(answer["ok"]))

        asyncio.run(run())

        assert (len(produced), len(cache)) == (2, 0)


def _chat(finish: str, message: dict[str, object]) -> Answer:
    return {"choices": [{"index": 0, "message": {"role": "assistant", **message}, "finish_reason": finish}]}


class TestWhatIsWorthReplaying:
    @pytest.mark.parametrize(
        ("answer", "worth"),
        [
            (_chat("stop", {"content": "hello"}), True),
            (_chat("tool_calls", {"content": None, "tool_calls": [{"id": "c"}]}), True),
            (_chat("function_call", {"content": None, "tool_calls": [{"id": "c"}]}), True),
            (_chat("length", {"content": "cut off"}), False),
            (_chat("content_filter", {"content": ""}), False),
            (_chat("stop", {"content": ""}), False),
            (_chat("stop", {"content": None}), False),
            ({"choices": []}, False),
            ({}, False),
        ],
        ids=["answer", "tool call", "function call", "truncated", "filtered", "empty", "null", "no choice", "nothing"],
    )
    def test_a_chat_answer_must_have_finished_normally_and_say_something(self, answer: Answer, worth: bool) -> None:
        assert CHAT.answer(answer) is worth

    @pytest.mark.parametrize(
        ("answer", "worth"),
        [
            ({"status": "completed", "output": [{"type": "message"}]}, True),
            ({"status": "completed", "output": []}, False),
            ({"status": "failed", "output": [{"type": "message"}]}, False),
            ({"status": "incomplete", "output": [{"type": "message"}]}, False),
            ({"output": [{"type": "message"}]}, False),
        ],
        ids=["completed", "empty", "failed", "incomplete", "no status"],
    )
    def test_a_responses_answer_must_be_a_completed_one_with_output(self, answer: Answer, worth: bool) -> None:
        assert RESPONSES.answer(answer) is worth

    def test_a_chat_chunk_carries_output_when_it_has_text_or_a_tool_call(self) -> None:
        text = {"choices": [{"delta": {"content": "hi"}}]}
        call = {"choices": [{"delta": {"tool_calls": [{"index": 0}]}}]}
        role_only = {"choices": [{"delta": {"role": "assistant"}}]}
        usage_only = {"choices": [], "usage": {"total_tokens": 3}}

        assert [CHAT.carries_output(c) for c in (text, call, role_only, usage_only)] == [True, True, False, False]

    def test_a_responses_event_carries_output_when_it_is_an_output_event(self) -> None:
        delta = {"type": "response.output_text.delta", "delta": "hi"}
        created = {"type": "response.created"}

        assert [RESPONSES.carries_output(c) for c in (delta, created)] == [True, False]

    def test_the_stored_form_is_compact_json_the_cache_can_serve_back(self, cache: AnswerCache) -> None:
        cached_answer(_request(), lambda: {"text": "héllo", "n": [1, 2]})

        key = request_key(_request())
        assert key is not None
        assert json.loads(cache.get(key) or "") == {"text": "héllo", "n": [1, 2]}


class TestReplayStreams:
    def test_a_replay_hands_out_its_chunks_and_the_finish_reason_it_recorded(self) -> None:
        replay = ReplayStream([{"a": 1}, {"b": 2}], "stop")

        assert (list(replay), replay.received_finish_reason) == ([{"a": 1}, {"b": 2}], "stop")

    def test_a_closed_replay_hands_out_nothing_more(self) -> None:
        replay = ReplayStream([{"a": 1}, {"b": 2}], "stop")
        assert next(replay) == {"a": 1}

        replay.close()

        assert list(replay) == []

    def test_the_async_replay_hands_out_its_chunks_and_stops_once_closed(self) -> None:
        async def run() -> tuple[list[object], list[object], str | None]:
            replay = AsyncReplayStream([{"a": 1}, {"b": 2}], "tool_calls")
            first = await anext(replay)
            await replay.aclose()
            return [first], [part async for part in replay], replay.received_finish_reason

        assert asyncio.run(run()) == ([{"a": 1}], [], "tool_calls")
