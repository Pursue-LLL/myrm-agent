"""Cutting a streamed response body into events: SSE, NDJSON and the AWS event stream.

[INPUT]
- httpx::Response (POS: the streamed body, read as lines or as bytes)
- transport.errors (POS: LLMResponseError for an event stream that is corrupted or cut off)

[OUTPUT]
- iter_stream_events / aiter_stream_events: the ``(event, data)`` pairs one response body carries in one framing

[POS]
Framing is the one thing a wire's decoder must not care about, so every protocol's body is reduced here to the same
pair: an optional event name and the text of its payload. SSE and NDJSON are line protocols. The AWS event stream
(Bedrock's ``converse-stream``) is binary: each message is a length prelude, typed headers, a payload and two CRC-32
checksums. An event message becomes ``(<event-type>, <payload>)``; an exception or error message becomes
``("exception:<type>", <payload>)`` or ``("error:<code>", <message>)``, so the decoder can fail the stream with the
provider's own words. A message that fails its checksum, or a body that stops inside one, is a stream that was cut or
corrupted on the way and fails like a cut-off JSON frame: the caller's retry produces the whole answer again.
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import AsyncIterator, Iterator
from typing import Final

import httpx

from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError

Event = tuple[str | None, str]

_PRELUDE: Final = 12  # total length, headers length, CRC-32 of those eight bytes
_TRAILER: Final = 4  # CRC-32 of everything before it
_MAX_MESSAGE: Final = 16 * 1024 * 1024
# Header value types that carry no length prefix, by the bytes they occupy; 6 (bytes) and 7 (string) carry a u16 length.
_FIXED_VALUE_SIZE: Final = {0: 0, 1: 0, 2: 1, 3: 2, 4: 4, 5: 8, 8: 8, 9: 16}
_STRING: Final = 7
_BYTES: Final = 6


class _SseParser:
    """Line-by-line SSE state machine: ``push`` returns an event when a blank line closes one."""

    __slots__ = ("_data", "_event")

    def __init__(self) -> None:
        self._event: str | None = None
        self._data: list[str] = []

    def push(self, line: str) -> Event | None:
        if not line:
            return self.flush()
        if line.startswith(":"):
            return None
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        return None

    def flush(self) -> Event | None:
        event, data = self._event, self._data
        self._event, self._data = None, []
        return (event, "\n".join(data)) if data else None


def _line_events(lines: Iterator[str], framing: str) -> Iterator[Event]:
    if framing == "ndjson":
        for line in lines:
            if line.strip():
                yield None, line
        return
    parser = _SseParser()
    for line in lines:
        if (event := parser.push(line)) is not None:
            yield event
    if (event := parser.flush()) is not None:
        yield event


async def _aline_events(lines: AsyncIterator[str], framing: str) -> AsyncIterator[Event]:
    if framing == "ndjson":
        async for line in lines:
            if line.strip():
                yield None, line
        return
    parser = _SseParser()
    async for line in lines:
        if (event := parser.push(line)) is not None:
            yield event
    if (event := parser.flush()) is not None:
        yield event


def _string_headers(block: bytes) -> dict[str, str]:
    """The string-valued headers of one message (``:event-type``, ``:message-type``, ...); other types are skipped."""
    headers: dict[str, str] = {}
    pos = 0
    while pos < len(block):
        name_end = pos + 1 + block[pos]
        name = block[pos + 1 : name_end].decode()
        kind = block[name_end]
        pos = name_end + 1
        if kind in _FIXED_VALUE_SIZE:
            pos += _FIXED_VALUE_SIZE[kind]
        elif kind in (_STRING, _BYTES):
            (length,) = struct.unpack_from(">H", block, pos)
            raw = block[pos + 2 : pos + 2 + length]
            pos += 2 + length
            if kind == _STRING:
                headers[name] = raw.decode()
        else:
            raise ValueError(f"unknown header value type {kind}")
    if pos != len(block):
        raise ValueError("a header runs past the end of its block")
    return headers


class _EventStreamParser:
    """Reassembles event-stream messages from arbitrary byte chunks."""

    __slots__ = ("_buffer", "_provider")

    def __init__(self, provider: str) -> None:
        self._buffer = bytearray()
        self._provider = provider

    def _corrupt(self, why: str) -> LLMResponseError:
        # Worded away from "invalid JSON": the classifier reads that as a model that produced bad output.
        return LLMResponseError(
            self._provider, f"{self._provider} sent an event stream that is cut off or corrupted ({why})"
        )

    def _message(self) -> Event | None:
        buffer = self._buffer
        if len(buffer) < _PRELUDE:
            return None
        total, header_length, prelude_crc = struct.unpack_from(">III", buffer)
        if zlib.crc32(bytes(buffer[:8])) != prelude_crc:
            raise self._corrupt("prelude checksum")
        if not _PRELUDE + header_length + _TRAILER <= total <= _MAX_MESSAGE:
            raise self._corrupt("message length")
        if len(buffer) < total:
            return None
        message = bytes(buffer[:total])
        del buffer[:total]
        if zlib.crc32(message[:-_TRAILER]) != struct.unpack(">I", message[-_TRAILER:])[0]:
            raise self._corrupt("message checksum")
        try:
            headers = _string_headers(message[_PRELUDE : _PRELUDE + header_length])
            payload = message[_PRELUDE + header_length : -_TRAILER].decode("utf-8", "replace")
        except (ValueError, IndexError, struct.error) as exc:
            raise self._corrupt("headers") from exc
        kind = headers.get(":message-type")
        if kind == "exception":
            return f"exception:{headers.get(':exception-type', '')}", payload
        if kind == "error":
            return f"error:{headers.get(':error-code', '')}", headers.get(":error-message", payload)
        return headers.get(":event-type"), payload

    def feed(self, data: bytes) -> Iterator[Event]:
        self._buffer += data
        while (event := self._message()) is not None:
            yield event

    def close(self) -> None:
        if self._buffer:
            raise self._corrupt("the body ended inside a message")


def iter_stream_events(response: httpx.Response, framing: str, provider: str) -> Iterator[Event]:
    """The events of a streamed response body (``framing``: ``sse``, ``ndjson`` or ``eventstream``)."""
    if framing != "eventstream":
        yield from _line_events(response.iter_lines(), framing)
        return
    parser = _EventStreamParser(provider)
    for data in response.iter_bytes():
        yield from parser.feed(data)
    parser.close()


async def aiter_stream_events(response: httpx.Response, framing: str, provider: str) -> AsyncIterator[Event]:
    """Async twin of :func:`iter_stream_events`."""
    if framing != "eventstream":
        async for event in _aline_events(response.aiter_lines(), framing):
            yield event
        return
    parser = _EventStreamParser(provider)
    async for data in response.aiter_bytes():
        for event in parser.feed(data):
            yield event
    parser.close()
