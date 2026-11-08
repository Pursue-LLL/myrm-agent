"""Cutting a streamed body into events: the AWS event stream (Bedrock) and the line protocols (SSE, NDJSON).

The event stream is binary, so what matters is what a network can do to it: deliver it in chunks of any size, cut it
off, flip a bit. Each of those either yields the same events or fails as a corrupted stream, never as a wrong answer.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.stream_events import Event, aiter_stream_events, iter_stream_events

from .event_stream_bodies import event, exception, framed, message, text_stream, typed_header

_EVENTS = [("messageStart", '{"role": "assistant"}'), ("messageStop", '{"stopReason": "end_turn"}')]
_BODY = b"".join([event("messageStart", {"role": "assistant"}), event("messageStop", {"stopReason": "end_turn"})])
_CORRUPTED = "cut off or corrupted"


def _chunks(body: bytes, size: int) -> list[bytes]:
    return [body[i : i + size] for i in range(0, len(body), size)] or [b""]


def _events(body: bytes, size: int | None = None, framing: str = "eventstream") -> list[Event]:
    response = httpx.Response(200, content=iter(_chunks(body, size or len(body) or 1)))
    return list(iter_stream_events(response, framing, "bedrock"))


async def _aevents(body: bytes, size: int | None = None, framing: str = "eventstream") -> list[Event]:
    async def stream() -> AsyncIterator[bytes]:
        for chunk in _chunks(body, size or len(body) or 1):
            yield chunk

    response = httpx.Response(200, content=stream())
    return [pair async for pair in aiter_stream_events(response, framing, "bedrock")]


def _corrupt(body: bytes) -> bytes:
    """``body`` with one payload bit flipped, which only the trailing checksum can see."""
    flipped = bytearray(body)
    flipped[-6] ^= 0x01
    return bytes(flipped)


class TestEventStream:
    def test_a_message_is_its_event_type_and_its_payload(self) -> None:
        assert _events(_BODY) == _EVENTS

    @pytest.mark.parametrize("size", [1, 2, 3, 7, 11, 12, 13, 64, 1000])
    def test_the_size_of_the_network_chunks_does_not_change_the_events(self, size: int) -> None:
        assert _events(_BODY, size) == _EVENTS

    @pytest.mark.parametrize("size", [1, 5, 1000])
    async def test_the_async_reader_agrees_for_any_chunk_size(self, size: int) -> None:
        assert await _aevents(_BODY, size) == _EVENTS

    def test_a_whole_conversation_is_read_in_order(self) -> None:
        names = [name for name, _ in _events(b"".join(text_stream("a", "b")), 9)]
        assert names == [
            "messageStart",
            "contentBlockDelta",
            "contentBlockDelta",
            "contentBlockStop",
            "messageStop",
            "metadata",
        ]

    def test_an_empty_body_has_no_events(self) -> None:
        assert _events(b"") == []

    def test_an_exception_message_carries_its_type_and_payload(self) -> None:
        assert _events(exception("throttlingException", "slow down")) == [
            ("exception:throttlingException", '{"message": "slow down"}')
        ]

    def test_an_error_message_carries_the_text_of_its_header(self) -> None:
        body = message({":message-type": "error", ":error-code": "InternalFailure", ":error-message": "boom"})
        assert _events(body) == [("error:InternalFailure", "boom")]

    def test_an_error_message_without_text_falls_back_to_its_payload(self) -> None:
        body = message({":message-type": "error", ":error-code": "X"}, b"details")
        assert _events(body) == [("error:X", "details")]

    def test_an_exception_message_without_a_type_is_still_an_exception(self) -> None:
        assert _events(message({":message-type": "exception"}, b"{}")) == [("exception:", "{}")]

    def test_a_message_without_a_type_has_no_event_name(self) -> None:
        assert _events(message({":content-type": "application/json"}, b"{}")) == [(None, "{}")]

    def test_headers_of_every_other_type_are_skipped_not_misread(self) -> None:
        block = b"".join(
            [
                typed_header("flag-true", 0),
                typed_header("flag-false", 1),
                typed_header("byte", 2, b"\x01"),
                typed_header("short", 3, b"\x00\x02"),
                typed_header("int", 4, b"\x00\x00\x00\x03"),
                typed_header("long", 5, b"\x00" * 8),
                typed_header("blob", 6, b"\x00\x03abc"),
                typed_header("when", 8, b"\x00" * 8),
                typed_header("id", 9, b"\x00" * 16),
                typed_header(":event-type", 7, b"\x00\x0bmessageStop"),
            ]
        )
        assert _events(framed(block, b"{}")) == [("messageStop", "{}")]

    def test_a_payload_that_is_not_utf8_is_replaced_not_fatal(self) -> None:
        body = message({":event-type": "x", ":message-type": "event"}, b"\xff\xfe")
        assert _events(body) == [("x", "\ufffd\ufffd")]

    def test_the_payload_may_hold_text_of_any_script(self) -> None:
        body = message({":event-type": "x", ":message-type": "event"}, "日本語".encode())
        assert _events(body) == [("x", "日本語")]


class TestCorruptedStreams:
    def test_a_flipped_payload_bit_fails_the_message_checksum(self) -> None:
        with pytest.raises(LLMResponseError, match=r"\(message checksum\)"):
            _events(_corrupt(_BODY))

    def test_a_flipped_prelude_bit_fails_the_prelude_checksum(self) -> None:
        flipped = bytearray(_BODY)
        flipped[1] ^= 0x01
        with pytest.raises(LLMResponseError, match=r"\(prelude checksum\)"):
            _events(bytes(flipped))

    def test_a_prelude_checksum_that_is_wrong_is_refused_even_when_the_rest_of_the_message_checks_out(self) -> None:
        (total,) = struct.unpack_from(">I", _BODY)
        damaged = bytearray(_BODY[:total])
        damaged[8] ^= 0x01
        damaged[-4:] = struct.pack(">I", zlib.crc32(bytes(damaged[:-4])))
        with pytest.raises(LLMResponseError, match=r"\(prelude checksum\)"):
            _events(bytes(damaged))

    @pytest.mark.parametrize("cut", [1, 5, 11, 13, 40])
    def test_a_body_that_ends_inside_a_message_fails_instead_of_ending_quietly(self, cut: int) -> None:
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(_BODY[:-cut] if cut < len(_BODY) else b"")

    async def test_the_async_reader_fails_the_same_way(self) -> None:
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            await _aevents(_BODY[:-3], 4)
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            await _aevents(_corrupt(_BODY), 4)

    def test_the_events_before_the_damage_are_still_delivered(self) -> None:
        delivered: list[Event] = []
        response = httpx.Response(200, content=iter([_BODY[:-3]]))
        with pytest.raises(LLMResponseError):
            for pair in iter_stream_events(response, "eventstream", "bedrock"):
                delivered.append(pair)
        assert delivered == _EVENTS[:1]

    def test_a_length_beyond_the_limit_is_refused_before_it_is_buffered(self) -> None:
        prelude = struct.pack(">II", 17 * 1024 * 1024, 0)
        prelude += struct.pack(">I", zlib.crc32(prelude))
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(prelude + b"x" * 64)

    def test_headers_longer_than_the_message_are_refused(self) -> None:
        prelude = struct.pack(">II", 20, 500)
        prelude += struct.pack(">I", zlib.crc32(prelude))
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(prelude + b"\x00" * 8)

    def test_a_header_type_the_protocol_does_not_define_is_corruption(self) -> None:
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(framed(typed_header("odd", 10), b"{}"))

    def test_a_header_that_runs_past_its_block_is_corruption(self) -> None:
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(framed(typed_header("blob", 7, b"\x00\xff"), b"{}"))

    def test_a_header_name_that_is_not_text_is_corruption(self) -> None:
        with pytest.raises(LLMResponseError, match=_CORRUPTED):
            _events(framed(b"\x02\xff\xfe\x00", b"{}"))

    def test_the_error_names_the_provider_and_avoids_words_the_classifier_reads_as_bad_output(self) -> None:
        with pytest.raises(LLMResponseError) as caught:
            _events(_corrupt(_BODY))
        assert "bedrock" in str(caught.value)
        assert "json" not in str(caught.value).lower()


def _lines(*lines: str, framing: str) -> list[Event]:
    return _events("".join(f"{line}\n" for line in lines).encode(), framing=framing)


class TestLineFraming:
    def test_an_sse_event_may_be_named_and_spread_over_lines(self) -> None:
        assert _lines("event: message_start", "data: a", "data: b", "", framing="sse") == [("message_start", "a\nb")]

    def test_a_data_line_without_the_space_is_read_the_same(self) -> None:
        assert _lines("data:x", "", framing="sse") == [(None, "x")]

    def test_comments_and_unknown_fields_are_ignored(self) -> None:
        assert _lines(": keep-alive", "id: 7", "retry: 5", "data: x", "", framing="sse") == [(None, "x")]

    def test_an_event_name_applies_to_one_event_only(self) -> None:
        assert _lines("event: a", "data: 1", "", "data: 2", "", framing="sse") == [("a", "1"), (None, "2")]

    def test_an_event_without_data_is_dropped(self) -> None:
        assert _lines("event: ping", "", "data: x", "", framing="sse") == [(None, "x")]

    def test_the_last_event_counts_even_when_the_body_ends_without_a_blank_line(self) -> None:
        assert _events(b"data: tail", framing="sse") == [(None, "tail")]

    def test_ndjson_is_one_event_per_non_blank_line(self) -> None:
        assert _lines('{"a": 1}', "", "  ", '{"b": 2}', framing="ndjson") == [(None, '{"a": 1}'), (None, '{"b": 2}')]

    async def test_the_async_reader_reads_both_line_protocols_alike(self) -> None:
        assert await _aevents(b"event: e\ndata: a\n\ndata: b", framing="sse") == [("e", "a"), (None, "b")]
        assert await _aevents(b'{"a": 1}\n\n{"b": 2}\n', framing="ndjson") == [(None, '{"a": 1}'), (None, '{"b": 2}')]


def test_the_iterators_are_lazy() -> None:
    """A consumer that stops early never reads (or fails on) the rest of the body."""
    body = _BODY + _corrupt(_BODY)
    stream: Iterator[Event] = iter_stream_events(httpx.Response(200, content=iter([body])), "eventstream", "bedrock")
    assert next(stream) == _EVENTS[0]
