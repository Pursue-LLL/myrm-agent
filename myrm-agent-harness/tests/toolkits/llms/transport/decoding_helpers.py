"""Shared steps of the response-decoding tests: feed framed events to a decoder and read the first choice."""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.llms.transport.http import Chunk, StreamDecoder

Payload = dict[str, object]


def feed_events(decoder: StreamDecoder, events: list[tuple[str | None, Payload | str]]) -> list[Chunk]:
    """Feed events the way the framing layer does, stopping when the decoder says the stream is over."""
    chunks: list[Chunk] = []
    for event, data in events:
        chunks.extend(decoder.feed(event, data if isinstance(data, str) else json.dumps(data)))
        if decoder.done:
            break
    chunks.extend(decoder.finish())
    return chunks


def first_delta(chunk: Chunk) -> dict[str, object]:
    choices = chunk["choices"]
    assert isinstance(choices, list)
    delta = choices[0]["delta"]
    assert isinstance(delta, dict)
    return delta


def first_finish_reason(chunk: Chunk) -> object:
    choices = chunk["choices"]
    assert isinstance(choices, list)
    return choices[0]["finish_reason"]
