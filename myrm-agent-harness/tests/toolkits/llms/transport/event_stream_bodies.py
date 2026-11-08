"""AWS event-stream messages as Bedrock's ConverseStream sends them, and Converse answers, for the Bedrock wire tests."""

from __future__ import annotations

import json
import struct
import zlib

Body = dict[str, object]
CONTENT_TYPE = "application/vnd.amazon.eventstream"
USAGE: Body = {"inputTokens": 9, "outputTokens": 5, "totalTokens": 14}

_STRING = 7


def _header(name: str, value: str) -> bytes:
    raw_name, raw_value = name.encode(), value.encode()
    return (
        struct.pack(">B", len(raw_name)) + raw_name + bytes([_STRING]) + struct.pack(">H", len(raw_value)) + raw_value
    )


def framed(block: bytes, payload: bytes = b"") -> bytes:
    """One event-stream message around an encoded header block: prelude, headers, payload and the checksums of both."""
    prelude = struct.pack(">II", 12 + len(block) + len(payload) + 4, len(block))
    prelude += struct.pack(">I", zlib.crc32(prelude))
    body = prelude + block + payload
    return body + struct.pack(">I", zlib.crc32(body))


def typed_header(name: str, kind: int, value: bytes = b"") -> bytes:
    """A header whose value has any of the protocol's types (``value`` is the raw encoded value)."""
    raw_name = name.encode()
    return bytes([len(raw_name)]) + raw_name + bytes([kind]) + value


def message(headers: dict[str, str], payload: bytes = b"") -> bytes:
    """One event-stream message whose headers are all strings."""
    return framed(b"".join(_header(name, value) for name, value in headers.items()), payload)


def event(kind: str, body: Body) -> bytes:
    headers = {":event-type": kind, ":content-type": "application/json", ":message-type": "event"}
    return message(headers, json.dumps(body).encode())


def exception(kind: str, text: str) -> bytes:
    headers = {":exception-type": kind, ":content-type": "application/json", ":message-type": "exception"}
    return message(headers, json.dumps({"message": text}).encode())


def error(code: str, text: str) -> bytes:
    return message({":message-type": "error", ":error-code": code, ":error-message": text})


def delta(index: int, **fields: object) -> bytes:
    return event("contentBlockDelta", {"contentBlockIndex": index, "delta": dict(fields)})


def stop(index: int) -> bytes:
    return event("contentBlockStop", {"contentBlockIndex": index})


def tool_start(index: int, tool_use_id: str, name: str) -> bytes:
    start = {"toolUse": {"toolUseId": tool_use_id, "name": name}}
    return event("contentBlockStart", {"contentBlockIndex": index, "start": start})


def closing(reason: str = "end_turn", usage: Body | None = None) -> list[bytes]:
    """The two messages that end every answer: how it stopped, then what it cost."""
    return [
        event("messageStop", {"stopReason": reason}),
        event("metadata", {"usage": usage if usage is not None else dict(USAGE), "metrics": {"latencyMs": 3}}),
    ]


def text_stream(*pieces: str) -> list[bytes]:
    return [
        event("messageStart", {"role": "assistant"}),
        *(delta(0, text=piece) for piece in pieces),
        stop(0),
        *closing(),
    ]


def converse_answer(*blocks: Body, reason: str = "end_turn", usage: Body | None = None) -> Body:
    """A ``converse`` answer whose message holds ``blocks``."""
    return {
        "output": {"message": {"role": "assistant", "content": list(blocks) or [{"text": "hello"}]}},
        "stopReason": reason,
        "usage": usage if usage is not None else dict(USAGE),
        "metrics": {"latencyMs": 1},
    }
