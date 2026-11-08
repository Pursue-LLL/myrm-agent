"""Randomised Responses streams: whatever mix of events a server sends, the consumer gets each call exactly once.

Every case draws a "true" response (function calls with ids, names and argument objects, text, a reasoning summary,
usage) and renders it as an event stream in a randomly chosen dialect per call: announced or not, arguments as deltas,
on ``done`` only, whole on ``output_item.done``, whole on ``added`` and replayed as deltas, or only on
``response.completed``; events named by item id, call id or both; parallel calls at distinct or identical output
positions; calls interleaved with text and reasoning. The stream runs through the production decoder and the adapter's
tool-call aggregator, and what comes out must equal the response that was drawn. The generator is seeded: a failure
names the seed that reproduces it.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import pytest

from myrm_agent_harness.toolkits.llms.adapters.streaming import aggregate_tool_call_chunk, build_tool_call_chunks
from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import stream_responses_sync

type Event = dict[str, Any]
type ArgumentStyle = Literal["deltas", "done", "item_done", "bridge", "completed"]
type Identity = Literal["item", "call", "both"]

_SEEDS = range(600)
_STREAMED_STYLES: tuple[ArgumentStyle, ...] = ("deltas", "done", "item_done", "bridge")
_VALUES: tuple[object, ...] = (
    "Tokyo",
    'say "hi"',
    3,
    True,
    None,
    ["x", 1],
    {"k": "v"},
    "多字节",
    "line\nbreak",
    '{"a":1}',
)
_KEYS = ("city", "q", "path", "count", "flag", "payload", "目的地", "emoji")


@dataclass(frozen=True)
class Call:
    call_id: str
    item_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Dialect:
    announced: bool
    style: ArgumentStyle
    identity: Identity
    with_done: bool
    with_item_done: bool
    blank_empty: bool  # a call without parameters is sent as "" instead of "{}"


@dataclass(frozen=True)
class Drawn:
    events: list[Event]
    calls: list[Call]
    text: str
    reasoning: str
    usage: tuple[int, int]


def _arguments(rng: random.Random) -> str:
    keys = rng.sample(_KEYS, rng.randint(0, 3))
    return json.dumps({key: rng.choice(_VALUES) for key in keys}, ensure_ascii=rng.random() < 0.5)


def _pieces(rng: random.Random, text: str) -> list[str]:
    """``text`` cut at random places into non-empty pieces (a cut may fall inside a multi-byte character's escape)."""
    if len(text) < 2:
        return [text] if text else []
    cuts = sorted(rng.sample(range(1, len(text)), rng.randint(0, min(5, len(text) - 1))))
    return [text[start:end] for start, end in zip([0, *cuts], [*cuts, len(text)], strict=True)]


def _item(call: Call, *, arguments: str, status: str) -> Event:
    return {
        "type": "function_call",
        "id": call.item_id,
        "call_id": call.call_id,
        "name": call.name,
        "arguments": arguments,
        "status": status,
    }


def _on_wire(call: Call, dialect: Dialect) -> str:
    """The arguments string a server writes into a field that carries them whole."""
    return "" if dialect.blank_empty and call.arguments == "{}" else call.arguments


def _named(call: Call, dialect: Dialect) -> Event:
    """The identifiers an argument event carries under the dialect's naming."""
    named: Event = {}
    if dialect.identity in ("item", "both"):
        named["item_id"] = call.item_id
    if dialect.identity in ("call", "both"):
        named["call_id"] = call.call_id
    return named


def _call_events(rng: random.Random, call: Call, dialect: Dialect, position: int) -> list[Event]:
    """The events one call produces, in the order a server keeps for it (at least one, unless it only closes)."""
    if dialect.style == "completed":
        return []
    at = {"output_index": position}
    whole = _on_wire(call, dialect)
    events: list[Event] = []
    if dialect.announced:
        item = _item(call, arguments=whole if dialect.style == "bridge" else "", status="in_progress")
        events.append({"type": "response.output_item.added", **at, "item": item})
    if dialect.style in ("deltas", "bridge"):
        events += [
            {"type": "response.function_call_arguments.delta", **at, **_named(call, dialect), "delta": piece}
            for piece in _pieces(rng, whole)
        ]
    done = {
        "type": "response.function_call_arguments.done",
        **at,
        **_named(call, dialect),
        "name": call.name,
        "arguments": whole,
    }
    if dialect.style in ("deltas", "bridge", "done") and (dialect.with_done or dialect.style == "done"):
        events.append(done)
    if dialect.with_item_done or dialect.style == "item_done":
        events.append(
            {"type": "response.output_item.done", **at, "item": _item(call, arguments=whole, status="completed")}
        )
    return events or [done]


def _merge(rng: random.Random, queues: list[list[Event]], *, calls: int) -> Iterator[Event]:
    """Interleave the queues at random, each in its own order; the first ``calls`` queues are function calls, and a
    call starts only after every earlier call has started (servers number items in announcement order)."""
    pending = [list(queue) for queue in queues]
    has_events = [bool(queue) for queue in queues]
    started = [False] * len(queues)
    while any(pending):
        open_queues = [
            i
            for i, queue in enumerate(pending)
            if queue and (i >= calls or started[i] or all(started[j] or not has_events[j] for j in range(i)))
        ]
        chosen = rng.choice(open_queues)
        started[chosen] = True
        yield pending[chosen].pop(0)


def _draw(seed: int) -> Drawn:
    rng = random.Random(seed)
    call_count = rng.choice([0, 1, 1, 2, 2, 3, 4])
    completed_only = rng.randint(0, min(2, call_count)) if rng.random() < 0.3 else 0
    calls = [
        Call(
            f"call_{seed}_{n}",
            f"fc_{seed}_{n}",
            rng.choice(["get_weather", "search", "read_file", "x"]),
            _arguments(rng),
        )
        for n in range(call_count)
    ]
    text = "".join(rng.choice(["Hello ", "wor", "ld. ", "你好", "\n"]) for _ in range(rng.randint(0, 4)))
    reasoning = "".join(rng.choice(["Think ", "more. ", "思考"]) for _ in range(rng.randint(0, 3)))
    stream_reasoning = bool(reasoning) and rng.random() < 0.7
    usage = (rng.randint(1, 5000), rng.randint(1, 900))

    leading = int(bool(reasoning)) + int(bool(text))  # items before the first call in the response output
    same_position = rng.random() < 0.25
    queues: list[list[Event]] = []
    dialects: list[Dialect] = []
    for n, call in enumerate(calls):
        streamed = n < call_count - completed_only
        style: ArgumentStyle = rng.choice(_STREAMED_STYLES) if streamed else "completed"
        announced = style == "bridge" or (streamed and rng.random() < 0.8)
        identity: Identity = (
            "both" if style in ("done", "item_done") and not announced else rng.choice(["item", "call", "both"])
        )
        dialect = Dialect(announced, style, identity, rng.random() < 0.8, rng.random() < 0.8, rng.random() < 0.4)
        dialects.append(dialect)
        queues.append(_call_events(rng, call, dialect, 0 if same_position else leading + n))
    call_queue_count = len(queues)
    text_events = (
        [
            {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "delta": piece}
            for piece in _pieces(rng, text)
        ]
        if text
        else []
    )
    reasoning_events = (
        [
            {"type": "response.reasoning_summary_text.delta", "item_id": "rs_1", "output_index": 0, "delta": piece}
            for piece in _pieces(rng, reasoning)
        ]
        if stream_reasoning
        else []
    )
    queues += [text_events, reasoning_events]
    stream = list(_merge(rng, queues, calls=call_queue_count))

    output: list[Event] = []
    if reasoning:
        output.append({"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": reasoning}]})
    if text:
        output.append(
            {"type": "message", "id": "msg_1", "role": "assistant", "content": [{"type": "output_text", "text": text}]}
        )
    output += [
        _item(call, arguments=_on_wire(call, d), status="completed") for call, d in zip(calls, dialects, strict=True)
    ]
    completed = {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "output": output,
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
        },
    }
    events = [{"type": "response.created", "response": {"status": "in_progress"}}, *stream, completed]
    return Drawn(events, calls, text, reasoning, usage)


class _Client:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def responses(self, **_kwargs: object) -> Iterator[Event]:
        return iter(self._events)


@dataclass
class _Consumed:
    tool_calls: list[dict[str, Any]]
    text: str
    reasoning: str
    finish_reason: str | None
    usage: dict[str, int] | None


def _consume(events: list[Event]) -> _Consumed:
    tool_calls: list[dict[str, Any]] = []
    text: list[str] = []
    reasoning: list[str] = []
    finish: str | None = None
    usage: dict[str, int] | None = None
    for chunk in stream_responses_sync(_Client(events), [], {}):
        delta = chunk["choices"][0]["delta"]
        for tool_call_chunk in build_tool_call_chunks(delta.get("tool_calls")):
            aggregate_tool_call_chunk(tool_call_chunk, tool_calls)
        text.append(delta.get("content") or "")
        reasoning.append(delta.get("reasoning_content") or "")
        finish = chunk["choices"][0]["finish_reason"] or finish
        usage = chunk.get("usage") or usage
    return _Consumed(tool_calls, "".join(text), "".join(reasoning), finish, usage)


def _mismatch(seed: int) -> str | None:
    drawn = _draw(seed)
    got = _consume(drawn.events)
    expected = [(c.call_id, c.name, c.arguments) for c in drawn.calls]
    actual = [(c["id"], c["function"]["name"], c["function"]["arguments"]) for c in got.tool_calls]
    problems: list[str] = []
    if actual != expected:
        problems.append(f"tool calls {actual} != {expected}")
    if got.text != drawn.text:
        problems.append(f"text {got.text!r} != {drawn.text!r}")
    if got.reasoning != drawn.reasoning:
        problems.append(f"reasoning {got.reasoning!r} != {drawn.reasoning!r}")
    if got.finish_reason != ("tool_calls" if drawn.calls else "stop"):
        problems.append(f"finish_reason {got.finish_reason!r} with {len(drawn.calls)} calls")
    if got.usage is None or (got.usage["prompt_tokens"], got.usage["completion_tokens"]) != drawn.usage:
        problems.append(f"usage {got.usage} != {drawn.usage}")
    return f"seed {seed}: " + "; ".join(problems) if problems else None


def test_whatever_dialect_a_server_speaks_the_consumer_gets_each_call_once_whole_and_in_order() -> None:
    failures = [message for seed in _SEEDS if (message := _mismatch(seed))]

    assert not failures, f"{len(failures)} of {len(_SEEDS)} streams decoded wrongly; first: {failures[:3]}"


def test_the_generator_covers_every_dialect_and_shape() -> None:
    """A property test that never draws the interesting cases proves nothing: count what the seeds produce."""
    drawn = [_draw(seed) for seed in _SEEDS]
    kinds = {event["type"] for d in drawn for event in d.events}

    assert {
        "response.output_item.added",
        "response.function_call_arguments.delta",
        "response.function_call_arguments.done",
        "response.output_item.done",
        "response.output_text.delta",
        "response.reasoning_summary_text.delta",
    } <= kinds
    assert max(len(d.calls) for d in drawn) >= 4
    assert any(not d.calls for d in drawn)
    assert sum(len(d.calls) > 1 for d in drawn) > 100  # parallel calls are common, not an afterthought
    assert any(d.text and d.reasoning and d.calls for d in drawn)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_a_seed_always_draws_the_same_stream(seed: int) -> None:
    assert _draw(seed) == _draw(seed)
