"""Bedrock converse-stream reasoning: signed and redacted blocks reach the caller whole, when their content block stops.

The reasoning text streams as it arrives; the signature and a redaction only mean something together with the block they
belong to, so the decoder keeps one draft per content-block index and hands the finished block out on its stop event.
"""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.llms.transport import bedrock_response
from myrm_agent_harness.toolkits.llms.transport.bedrock_response import BedrockStreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

Body = dict[str, object]
Event = tuple[str, str]
ROUTE = resolve_route("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", api_key="k")


def _event(kind: str, **body: object) -> Event:
    return kind, json.dumps(body)


def _play(*events: Event) -> list[Body]:
    """Every chunk the decoder hands out for ``events``, then the chunks it adds when the body ends."""
    decoder = bedrock_response.decoder(ROUTE)
    assert isinstance(decoder, BedrockStreamDecoder)
    chunks: list[Body] = []
    for kind, data in events:
        chunks.extend(decoder.feed(kind, data))
    chunks.extend(decoder.finish())
    return chunks


def _delta(chunk: Body) -> Body:
    return chunk["choices"][0]["delta"]


def _stop(index: int) -> Event:
    return _event("contentBlockStop", contentBlockIndex=index)


def _reasoning(index: int, **piece: str) -> Event:
    """A reasoning delta: ``text``, ``signature`` or ``redactedContent``."""
    return _event("contentBlockDelta", contentBlockIndex=index, delta={"reasoningContent": piece})


def test_reasoning_text_is_streamed_and_the_signed_block_arrives_whole_when_its_index_stops() -> None:
    chunks = _play(
        _reasoning(0, text="think"),
        _reasoning(0, text="ing"),
        _reasoning(0, signature="sig"),
        _stop(0),
    )
    assert [_delta(c) for c in chunks] == [
        {"reasoning_content": "think"},
        {"reasoning_content": "ing"},
        {"thinking_blocks": [{"type": "thinking", "thinking": "thinking", "signature": "sig"}]},
    ]


def test_a_redacted_block_arrives_whole_when_its_index_stops() -> None:
    chunks = _play(_reasoning(1, redactedContent="QUJD"), _stop(1))
    assert [_delta(c) for c in chunks] == [{"thinking_blocks": [{"type": "redacted_thinking", "data": "QUJD"}]}]


def test_reasoning_without_a_signature_is_streamed_but_never_becomes_a_block() -> None:
    chunks = _play(_reasoning(0, text="unsigned"), _stop(0))
    assert [_delta(c) for c in chunks] == [{"reasoning_content": "unsigned"}]


def test_a_stream_cut_before_its_block_stops_hands_back_no_block() -> None:
    chunks = _play(_reasoning(0, text="think"), _reasoning(0, signature="sig"))
    assert [_delta(c) for c in chunks] == [{"reasoning_content": "think"}]


def test_interleaved_reasoning_blocks_are_kept_apart_by_their_index() -> None:
    chunks = _play(
        _reasoning(0, text="a"),
        _reasoning(1, redactedContent="QUJD"),
        _reasoning(0, signature="s0"),
        _stop(1),
        _stop(0),
    )
    assert [_delta(c) for c in chunks if "thinking_blocks" in _delta(c)] == [
        {"thinking_blocks": [{"type": "redacted_thinking", "data": "QUJD"}]},
        {"thinking_blocks": [{"type": "thinking", "thinking": "a", "signature": "s0"}]},
    ]
