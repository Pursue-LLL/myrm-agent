"""Signed reasoning in an Anthropic event stream: each block is handed over whole, exactly as the provider closed it.

The next request must return a block byte for byte, so the decoder assembles it from its deltas and releases it only
at ``content_block_stop``: by then the signature, which arrives last, is complete.
"""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.llms.transport import anthropic_response
from myrm_agent_harness.toolkits.llms.transport.http import Chunk
from myrm_agent_harness.toolkits.llms.transport.profile import resolve_route

from .decoding_helpers import Payload, feed_events, first_delta

_ROUTE = resolve_route("anthropic/claude-sonnet-4-5", api_key="k")
Event = tuple[str | None, Payload | str]


def _start(index: int, block: Payload) -> Event:
    return "content_block_start", {"type": "content_block_start", "index": index, "content_block": block}


def _delta(index: int, delta: Payload) -> Event:
    return "content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}


def _stop(index: int) -> Event:
    return "content_block_stop", {"type": "content_block_stop", "index": index}


def _thinking_part(index: int, text: str) -> Event:
    return _delta(index, {"type": "thinking_delta", "thinking": text})


def _signature_part(index: int, signature: str) -> Event:
    return _delta(index, {"type": "signature_delta", "signature": signature})


def _stream(*events: Event) -> list[Event]:
    opening: Event = "message_start", {"type": "message_start", "message": {"id": "msg_1", "model": "m"}}
    closing: list[Event] = [
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return [opening, *events, *closing]


def _handed_over(chunks: list[Chunk]) -> list[object]:
    """The blocks the stream hands over, in the order it released them."""
    blocks: list[object] = []
    for chunk in chunks:
        carried = first_delta(chunk).get("thinking_blocks")
        if isinstance(carried, list):
            blocks.extend(carried)
    return blocks


def _decode(*events: Event) -> list[Chunk]:
    return feed_events(anthropic_response.decoder(_ROUTE), _stream(*events))


class TestSignedBlocks:
    def test_a_block_is_released_at_its_close_with_the_text_and_signature_of_all_its_deltas(self) -> None:
        chunks = _decode(
            _start(0, {"type": "thinking", "thinking": ""}),
            _thinking_part(0, "Let me "),
            _thinking_part(0, "check."),
            _signature_part(0, "sig-"),
            _signature_part(0, "1"),
            _stop(0),
        )

        assert _handed_over(chunks) == [{"type": "thinking", "thinking": "Let me check.", "signature": "sig-1"}]

    def test_the_text_a_block_opens_with_is_part_of_it(self) -> None:
        chunks = _decode(_start(0, {"type": "thinking", "thinking": "Hm."}), _signature_part(0, "s"), _stop(0))

        assert _handed_over(chunks) == [{"type": "thinking", "thinking": "Hm.", "signature": "s"}]

    def test_nothing_is_handed_over_before_the_block_closes(self) -> None:
        decoder = anthropic_response.decoder(_ROUTE)
        opened = _stream(
            _start(0, {"type": "thinking", "thinking": ""}), _thinking_part(0, "hm"), _signature_part(0, "sig")
        )[:-2]

        fed = [
            chunk
            for event, data in opened
            for chunk in decoder.feed(event, data if isinstance(data, str) else json.dumps(data))
        ]

        assert _handed_over(fed) == []

    def test_a_block_that_ended_unsigned_is_not_handed_over(self) -> None:
        chunks = _decode(_start(0, {"type": "thinking", "thinking": ""}), _thinking_part(0, "hm"), _stop(0))

        assert _handed_over(chunks) == []

    def test_a_signed_block_without_text_is_still_a_block(self) -> None:
        chunks = _decode(_start(0, {"type": "thinking", "thinking": ""}), _signature_part(0, "sig"), _stop(0))

        assert _handed_over(chunks) == [{"type": "thinking", "thinking": "", "signature": "sig"}]

    def test_a_redacted_block_arrives_whole_at_its_start_and_is_released_at_its_close(self) -> None:
        chunks = _decode(_start(0, {"type": "redacted_thinking", "data": "opaque"}), _stop(0))

        assert _handed_over(chunks) == [{"type": "redacted_thinking", "data": "opaque"}]

    def test_blocks_keep_the_order_the_provider_closed_them_in(self) -> None:
        chunks = _decode(
            _start(0, {"type": "redacted_thinking", "data": "opaque"}),
            _stop(0),
            _start(1, {"type": "thinking", "thinking": ""}),
            _thinking_part(1, "second"),
            _signature_part(1, "sig-2"),
            _stop(1),
            _start(2, {"type": "text", "text": ""}),
            _delta(2, {"type": "text_delta", "text": "answer"}),
            _stop(2),
        )

        assert _handed_over(chunks) == [
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "thinking", "thinking": "second", "signature": "sig-2"},
        ]

    def test_a_tool_turn_hands_over_its_reasoning_before_the_tool_call_completes(self) -> None:
        chunks = _decode(
            _start(0, {"type": "thinking", "thinking": ""}),
            _signature_part(0, "sig"),
            _stop(0),
            _start(1, {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {}}),
            _delta(1, {"type": "input_json_delta", "partial_json": "{}"}),
            _stop(1),
        )
        deltas = [first_delta(chunk) for chunk in chunks]

        assert [key for delta in deltas for key in delta if key in {"thinking_blocks", "tool_calls"}] == [
            "thinking_blocks",
            "tool_calls",
            "tool_calls",
        ]

    def test_the_reasoning_text_still_streams_as_it_arrives(self) -> None:
        chunks = _decode(
            _start(0, {"type": "thinking", "thinking": ""}), _thinking_part(0, "a"), _signature_part(0, "s"), _stop(0)
        )

        assert [
            first_delta(chunk)["reasoning_content"] for chunk in chunks if "reasoning_content" in first_delta(chunk)
        ] == ["a"]
