"""Responses stream decoding: every function call arrives once, whole, under its own index.

The event sequences follow what live Responses servers send (item announced with empty arguments, arguments as
``item_id``-addressed deltas, then replayed whole on ``arguments.done``, ``output_item.done`` and
``response.completed``) plus the variants other servers and bridges produce. Each sequence runs through the
production path: ``stream_responses_sync`` / ``stream_responses_async`` and the adapter's tool-call aggregator.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

from myrm_agent_harness.toolkits.llms.adapters.streaming import aggregate_tool_call_chunk, build_tool_call_chunks
from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import stream_responses_async, stream_responses_sync
from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import (
    responses_dict_to_chat_completion,
    responses_event_to_completion_chunk,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.responses_stream import ResponsesStreamState
from myrm_agent_harness.utils.token_economics.usage_fields import extract_cached_tokens, extract_reasoning_tokens

type Event = dict[str, Any]

TOKYO = ("call_tokyo", "fc_tokyo", "get_weather", '{"city":"Tokyo"}')
PARIS = ("call_paris", "fc_paris", "get_weather", '{"city":"Paris"}')


def _item(call: tuple[str, str, str, str], *, arguments: str | None = None, status: str = "completed") -> Event:
    call_id, item_id, name, args = call
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id,
        "name": name,
        "arguments": args if arguments is None else arguments,
        "status": status,
    }


def _added(call: tuple[str, str, str, str], index: int, *, arguments: str = "") -> Event:
    item = _item(call, arguments=arguments, status="in_progress")
    return {"type": "response.output_item.added", "output_index": index, "item": item}


def _delta(call: tuple[str, str, str, str], index: int, piece: str) -> Event:
    return {
        "type": "response.function_call_arguments.delta",
        "item_id": call[1],
        "output_index": index,
        "delta": piece,
    }


def _args_done(call: tuple[str, str, str, str], index: int) -> Event:
    return {
        "type": "response.function_call_arguments.done",
        "item_id": call[1],
        "call_id": call[0],
        "name": call[2],
        "output_index": index,
        "arguments": call[3],
    }


def _item_done(call: tuple[str, str, str, str], index: int) -> Event:
    return {"type": "response.output_item.done", "output_index": index, "item": _item(call)}


def _completed(
    output: list[Event],
    *,
    usage: Event | None = None,
    status: str = "completed",
    event_type: str = "response.completed",
) -> Event:
    response: Event = {"status": status, "output": output}
    if usage:
        response["usage"] = usage
    return {"type": event_type, "response": response}


def _spec_call(call: tuple[str, str, str, str], index: int, *pieces: str) -> list[Event]:
    """One function call the way spec-compliant servers stream it."""
    return [
        _added(call, index),
        *(_delta(call, index, piece) for piece in pieces or (call[3],)),
        _args_done(call, index),
        _item_done(call, index),
    ]


class _Client:
    """Sync and async Responses client replaying fixed events."""

    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def responses(self, **_kwargs: object) -> Iterator[Event]:
        return iter(self._events)

    async def aresponses(self, **_kwargs: object) -> AsyncIterator[Event]:
        async def _events() -> AsyncIterator[Event]:
            for event in self._events:
                yield event

        return _events()


class _Decoded:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks
        self.tool_calls: list[dict[str, Any]] = []
        for chunk in chunks:
            for tool_call_chunk in build_tool_call_chunks(chunk["choices"][0]["delta"].get("tool_calls")):
                aggregate_tool_call_chunk(tool_call_chunk, self.tool_calls)

    def calls(self) -> list[tuple[str, str, dict[str, Any]]]:
        """(id, name, parsed arguments); parsing fails when arguments were duplicated or cut."""
        return [(c["id"], c["function"]["name"], json.loads(c["function"]["arguments"])) for c in self.tool_calls]

    @property
    def finish_reason(self) -> str | None:
        reasons = [c["choices"][0]["finish_reason"] for c in self.chunks if c["choices"][0]["finish_reason"]]
        return reasons[-1] if reasons else None

    def deltas(self, key: str) -> list[object]:
        return [c["choices"][0]["delta"][key] for c in self.chunks if key in c["choices"][0]["delta"]]


def _decode(events: list[Event]) -> _Decoded:
    return _Decoded(list(stream_responses_sync(_Client(events), [], {})))


WEATHER_OUTPUT = [_item(TOKYO)]
TOKYO_CALL = ("call_tokyo", "get_weather", {"city": "Tokyo"})
BOTH_CALLS = [TOKYO_CALL, ("call_paris", "get_weather", {"city": "Paris"})]


def test_spec_stream_with_item_id_deltas_yields_the_call_once() -> None:
    """MiniMax / Claude behind a Responses gateway: text item first, so the call sits at output_index 1."""
    events = [
        {"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "id": "msg_1"}},
        {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "delta": "Checking."},
        {"type": "response.output_item.done", "output_index": 0, "item": {"type": "message", "id": "msg_1"}},
        *_spec_call(TOKYO, 1, '{"city":', '"Tokyo"}'),
        _completed([{"type": "message", "id": "msg_1"}, _item(TOKYO)]),
    ]
    decoded = _decode(events)
    assert decoded.calls() == [TOKYO_CALL]
    assert decoded.deltas("content") == ["Checking."]
    assert decoded.finish_reason == "tool_calls"


def test_parallel_calls_stay_separate() -> None:
    events = [
        *_spec_call(TOKYO, 0),
        *_spec_call(PARIS, 1),
        _completed([_item(TOKYO), _item(PARIS)]),
    ]
    assert _decode(events).calls() == BOTH_CALLS


def test_interleaved_parallel_calls_stay_separate() -> None:
    events = [
        _added(TOKYO, 0),
        _added(PARIS, 1),
        _delta(TOKYO, 0, '{"city":'),
        _delta(PARIS, 1, '{"city":'),
        _delta(TOKYO, 0, '"Tokyo"}'),
        _delta(PARIS, 1, '"Paris"}'),
        _args_done(PARIS, 1),
        _args_done(TOKYO, 0),
        _item_done(TOKYO, 0),
        _item_done(PARIS, 1),
        _completed([_item(TOKYO), _item(PARIS)]),
    ]
    assert _decode(events).calls() == BOTH_CALLS


def test_parallel_calls_sharing_an_output_index_stay_separate() -> None:
    events = [*_spec_call(TOKYO, 0), *_spec_call(PARIS, 0), _completed([_item(TOKYO), _item(PARIS)])]
    assert _decode(events).calls() == BOTH_CALLS


def test_bridge_sending_arguments_whole_on_added_does_not_repeat_them() -> None:
    events = [
        _added(TOKYO, 0, arguments=TOKYO[3]),
        _delta(TOKYO, 0, TOKYO[3]),
        _args_done(TOKYO, 0),
        _item_done(TOKYO, 0),
        _completed(WEATHER_OUTPUT),
    ]
    assert _decode(events).calls() == [TOKYO_CALL]


def test_arguments_known_only_from_the_arguments_done_event() -> None:
    events = [_added(TOKYO, 0), _args_done(TOKYO, 0), _item_done(TOKYO, 0), _completed(WEATHER_OUTPUT)]
    assert _decode(events).calls() == [TOKYO_CALL]


def test_arguments_known_only_from_the_item_done_event() -> None:
    events = [_added(TOKYO, 0), _item_done(TOKYO, 0), _completed(WEATHER_OUTPUT)]
    assert _decode(events).calls() == [TOKYO_CALL]


def test_call_known_only_from_the_completed_event() -> None:
    decoded = _decode([_completed([_item(TOKYO), _item(PARIS)])])
    assert decoded.calls() == BOTH_CALLS
    assert decoded.finish_reason == "tool_calls"


def test_call_without_parameters_gets_an_empty_object() -> None:
    call = ("call_ping", "fc_ping", "ping", "")
    events = [_added(call, 0), _args_done(call, 0), _item_done(call, 0), _completed([_item(call)])]
    assert _decode(events).calls() == [("call_ping", "ping", {})]


def test_deltas_addressed_by_output_index_only() -> None:
    events = [
        _added(TOKYO, 2),
        {"type": "response.function_call_arguments.delta", "output_index": 2, "delta": TOKYO[3]},
        _completed(WEATHER_OUTPUT),
    ]
    assert _decode(events).calls() == [TOKYO_CALL]


def test_delta_before_the_call_was_announced_still_gets_its_provider_ids() -> None:
    events = [_delta(TOKYO, 0, TOKYO[3]), _completed(WEATHER_OUTPUT)]
    assert _decode(events).calls() == [TOKYO_CALL]


def test_streamed_calls_finish_as_tool_calls_even_when_completed_lists_no_output() -> None:
    decoded = _decode([*_spec_call(TOKYO, 0), _completed([])])
    assert decoded.calls() == [TOKYO_CALL]
    assert decoded.finish_reason == "tool_calls"


def test_plain_answer_finishes_as_stop() -> None:
    decoded = _decode([{"type": "response.output_text.delta", "delta": "hi"}, _completed([])])
    assert decoded.tool_calls == []
    assert decoded.finish_reason == "stop"


def test_incomplete_event_finishes_as_length_and_keeps_usage() -> None:
    usage = {"input_tokens": 7, "output_tokens": 600, "total_tokens": 607}
    decoded = _decode([_completed([], usage=usage, status="incomplete", event_type="response.incomplete")])
    assert decoded.finish_reason == "length"
    assert decoded.chunks[-1]["usage"] == {"prompt_tokens": 7, "completion_tokens": 600, "total_tokens": 607}


def test_each_stream_starts_with_fresh_call_indexes() -> None:
    events = [*_spec_call(TOKYO, 0), _completed(WEATHER_OUTPUT)]
    client = _Client(events)
    first = _Decoded(list(stream_responses_sync(client, [], {})))
    second = _Decoded(list(stream_responses_sync(client, [], {})))
    assert first.calls() == second.calls() == [TOKYO_CALL]


@pytest.mark.asyncio
async def test_async_stream_yields_the_call_once() -> None:
    events = [*_spec_call(TOKYO, 0), *_spec_call(PARIS, 1), _completed([_item(TOKYO), _item(PARIS)])]
    chunks = [chunk async for chunk in stream_responses_async(_Client(events), [], {})]
    assert _Decoded(chunks).calls() == BOTH_CALLS


def test_reasoning_summary_streams_live_and_is_not_repeated_on_completion() -> None:
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "Weigh. Decide."}]}
    events = [
        {"type": "response.reasoning_summary_text.delta", "item_id": "rs_1", "summary_index": 0, "delta": "Weigh. "},
        {"type": "response.reasoning_summary_text.delta", "item_id": "rs_1", "summary_index": 0, "delta": "Decide."},
        _completed([reasoning]),
    ]
    decoded = _decode(events)
    assert decoded.deltas("reasoning_content") == ["Weigh. ", "Decide."]
    assert decoded.deltas("responses_reasoning_items") == [
        [{"type": "reasoning", "id": "rs_1", "summary": reasoning["summary"]}]
    ]


def test_reasoning_summary_known_only_from_completion_is_delivered_there() -> None:
    reasoning = {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "Weigh. Decide."}]}
    assert _decode([_completed([reasoning])]).deltas("reasoning_content") == ["Weigh. Decide."]


def test_stateless_mapping_treats_one_event_as_the_whole_stream() -> None:
    chunk = responses_event_to_completion_chunk(_completed(WEATHER_OUTPUT))
    assert chunk is not None
    tool_call = chunk["choices"][0]["delta"]["tool_calls"][0]
    assert (tool_call["id"], tool_call["function"]) == ("call_tokyo", {"name": "get_weather", "arguments": TOKYO[3]})


USAGE = {
    "input_tokens": 696,
    "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 512},
    "output_tokens": 18,
    "output_tokens_details": {"reasoning_tokens": 11},
    "total_tokens": 714,
}


def test_stream_usage_keeps_cache_and_reasoning_token_details() -> None:
    usage = _decode([_completed([], usage=USAGE)]).chunks[-1]["usage"]
    assert usage == {
        "prompt_tokens": 696,
        "completion_tokens": 18,
        "total_tokens": 714,
        "prompt_tokens_details": {"cached_tokens": 512},
        "completion_tokens_details": {"reasoning_tokens": 11},
    }
    assert extract_cached_tokens(usage) == 512
    assert extract_reasoning_tokens(usage) == 11


def test_non_stream_usage_keeps_cache_and_reasoning_token_details() -> None:
    usage = responses_dict_to_chat_completion({"output": [], "usage": USAGE})["usage"]
    assert usage["prompt_tokens_details"] == {"cached_tokens": 512}
    assert usage["completion_tokens_details"] == {"reasoning_tokens": 11}


def test_usage_without_details_stays_flat() -> None:
    usage = {"input_tokens": 3, "output_tokens": 2}
    assert _decode([_completed([], usage=usage)]).chunks[-1]["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }


def test_cache_write_tokens_are_reported_when_present() -> None:
    usage = {
        "input_tokens": 9,
        "output_tokens": 1,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 8},
    }
    mapped = _decode([_completed([], usage=usage)]).chunks[-1]["usage"]
    assert mapped["prompt_tokens_details"] == {"cache_write_tokens": 8}


def test_state_resolves_a_call_by_any_of_its_names() -> None:
    state = ResponsesStreamState()
    assert state.has_calls is False
    state.on_item({"output_index": 0}, _item(TOKYO, arguments=""), done=False)
    assert state.has_calls is True
    # The call_id alone (legacy servers) finds the call announced with both names.
    assert state.on_arguments({"call_id": "call_tokyo", "delta": "{"}, final=False)[0]["index"] == 0
