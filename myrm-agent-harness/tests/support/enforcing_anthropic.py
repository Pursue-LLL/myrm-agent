"""An Anthropic Messages API double that enforces the rules for replayed reasoning blocks.

[INPUT]
- toolkits.llms.transport.http (POS: the HTTP client factories every model call goes through, replaced here by an in-process transport)

[OUTPUT]
- EnforcingAnthropic: answers a tool loop round by round, signs the reasoning it returns and refuses what the API refuses
- RequestRecord: what one request carried and how the double answered it

[POS]
A test of signed-reasoning replay needs a provider that checks the blocks, because a double that accepts anything
cannot tell a client that replays them correctly from one that does not. The rules enforced are the documented ones:
a block is bound to the exact prompt it was written under (system prompt, tools and every earlier message, those
messages taken without their own reasoning blocks); the blocks a request replays are one unbroken run of what was
written; and with thinking on, the tool turn awaiting its result must lead with a block.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final
from unittest.mock import patch

import httpx

from myrm_agent_harness.toolkits.llms.transport import http

type Json = dict[str, object]

_REASONING: Final = ("thinking", "redacted_thinking")
_BAD_SIGNATURE: Final = "messages.{index}.content.0: Invalid `signature` in `thinking` block"
_NO_LEADING_BLOCK: Final = (
    "messages.{index}.content.0.type: Expected `thinking` or `redacted_thinking`, but found `tool_use`"
)


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """What one request carried and how the double answered it."""

    status: int
    thinking: bool
    replayed: int
    reason: str = ""


@dataclass(frozen=True, slots=True)
class _Minted:
    """What a signature is bound to: the prompt before its block and the block that came before it."""

    prefix: str
    previous: str | None


@dataclass(frozen=True, slots=True)
class _Refusal:
    reason: str
    message: str


def _blocks(content: object) -> list[Json]:
    """A message's content as blocks, with cache markers and blank text removed, which the binding ignores."""
    items = [content] if isinstance(content, str) else content if isinstance(content, list) else []
    blocks: list[Json] = []
    for item in items:
        block: Json = (
            {"type": "text", "text": item} if isinstance(item, str) else dict(item) if isinstance(item, dict) else {}
        )
        block.pop("cache_control", None)
        if block.get("type") == "text":
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            block["text"] = text
        if block.get("type") == "tool_result":
            block["content"] = _blocks(block.get("content"))
        blocks.append(block)
    return blocks


def _turns(body: Json) -> list[Json]:
    messages = body.get("messages")
    return [turn for turn in messages if isinstance(turn, dict)] if isinstance(messages, list) else []


def _declared_tools(body: Json) -> list[Json]:
    tools = body.get("tools")
    if not isinstance(tools, list):
        return []
    declared = [{k: v for k, v in tool.items() if k != "cache_control"} for tool in tools if isinstance(tool, dict)]
    return sorted(declared, key=lambda tool: str(tool.get("name")))


def _prefix_digest(body: Json, upto: int) -> str:
    """The prompt a block written after ``upto`` messages is bound to."""
    visible = [
        {
            "role": turn.get("role"),
            "content": [b for b in _blocks(turn.get("content")) if b.get("type") not in _REASONING],
        }
        for turn in _turns(body)[:upto]
    ]
    payload = {"system": _blocks(body.get("system")), "tools": _declared_tools(body), "messages": visible}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _replayed(turns: Sequence[Json]) -> list[tuple[int, str]]:
    """``(message index, signature)`` of every reasoning block the request sends back, in order."""
    return [
        (index, str(block.get("signature", "")))
        for index, turn in enumerate(turns)
        if turn.get("role") == "assistant"
        for block in _blocks(turn.get("content"))
        if block.get("type") in _REASONING
    ]


def _tool_rounds_so_far(turns: Sequence[Json]) -> int:
    """Tool results the user's latest message has been answered with."""
    rounds = 0
    for turn in reversed(turns):
        if turn.get("role") != "user":
            continue
        if not any(block.get("type") == "tool_result" for block in _blocks(turn.get("content"))):
            break
        rounds += 1
    return rounds


def _sse(events: Sequence[Json]) -> bytes:
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()


def _halves(text: str) -> list[str]:
    """Two pieces, so every stream delivers a block's text and signature in more than one delta."""
    middle = len(text) // 2
    return [text[:middle], text[middle:]]


def _block_events(index: int, block: Json) -> list[Json]:
    kind = block["type"]
    if kind == "thinking":
        start: Json = {"type": "thinking", "thinking": ""}
        deltas = [{"type": "thinking_delta", "thinking": part} for part in _halves(str(block["thinking"]))]
        deltas += [{"type": "signature_delta", "signature": part} for part in _halves(str(block["signature"]))]
    elif kind == "tool_use":
        start = {**block, "input": {}}
        deltas = [{"type": "input_json_delta", "partial_json": part} for part in _halves(json.dumps(block["input"]))]
    else:
        start = {"type": "text", "text": ""}
        deltas = [{"type": "text_delta", "text": str(block["text"])}]
    return [
        {"type": "content_block_start", "index": index, "content_block": start},
        *({"type": "content_block_delta", "index": index, "delta": delta} for delta in deltas),
        {"type": "content_block_stop", "index": index},
    ]


@dataclass(slots=True)
class EnforcingAnthropic:
    """Answers a tool loop: ``tool_rounds`` tool calls to the user's message, then a text answer.

    Every answer to a request with thinking on opens with a freshly signed reasoning block. A request that breaks a
    rule is answered with the 400 the API gives, and its record says which rule.
    """

    tool_rounds: int
    tool_name: str = "read_file"
    requests: list[RequestRecord] = field(default_factory=list)
    _minted: dict[str, _Minted] = field(default_factory=dict, init=False, repr=False)

    @contextmanager
    def serving(self) -> Iterator[None]:
        """Send every model call of the transport, sync or async, to this double."""
        transport = httpx.MockTransport(self.handle)
        with (
            patch.object(http, "_sync_client", lambda proxy: httpx.Client(transport=transport)),
            patch.object(http, "_async_client", lambda proxy: httpx.AsyncClient(transport=transport)),
        ):
            yield

    @property
    def accepted(self) -> list[RequestRecord]:
        return [record for record in self.requests if record.status == 200]

    @property
    def refused(self) -> list[RequestRecord]:
        return [record for record in self.requests if record.status != 200]

    def _refusal(self, body: Json, turns: Sequence[Json], replayed: Sequence[tuple[int, str]]) -> _Refusal | None:
        for position, (index, signature) in enumerate(replayed):
            minted = self._minted.get(signature)
            if minted is None:
                return _Refusal("unknown signature", _BAD_SIGNATURE.format(index=index))
            if minted.prefix != _prefix_digest(body, index):
                return _Refusal("the prompt before the block changed", _BAD_SIGNATURE.format(index=index))
            if position > 0 and minted.previous != replayed[position - 1][1]:
                return _Refusal("the run of blocks has a gap", _BAD_SIGNATURE.format(index=index))
        awaiting = len(turns) - 2
        if "thinking" in body and awaiting >= 0 and turns[awaiting].get("role") == "assistant":
            content = _blocks(turns[awaiting].get("content"))
            calls_tool = any(block.get("type") == "tool_use" for block in content)
            if calls_tool and content[0].get("type") not in _REASONING:
                return _Refusal(
                    "the tool turn awaiting its result lacks a block", _NO_LEADING_BLOCK.format(index=awaiting)
                )
        return None

    def _answer(self, body: Json, turns: Sequence[Json], replayed: Sequence[tuple[int, str]]) -> list[Json]:
        number = len(self.accepted) + 1
        content: list[Json] = []
        if "thinking" in body:
            signature = f"sig-{number}"
            self._minted[signature] = _Minted(_prefix_digest(body, len(turns)), replayed[-1][1] if replayed else None)
            content.append({"type": "thinking", "thinking": f"reasoning {number}", "signature": signature})
        if not _declared_tools(body) or _tool_rounds_so_far(turns) >= self.tool_rounds:
            content.append({"type": "text", "text": "done"})
        else:
            call = {
                "type": "tool_use",
                "id": f"toolu_{number}",
                "name": self.tool_name,
                "input": {"path": f"/f{number}.txt"},
            }
            content.append(call)
        return content

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if not isinstance(body, dict):
            raise TypeError("a Messages request body is a JSON object")
        turns = _turns(body)
        replayed = _replayed(turns)
        thinking = "thinking" in body
        if (refusal := self._refusal(body, turns, replayed)) is not None:
            self.requests.append(RequestRecord(400, thinking, len(replayed), refusal.reason))
            error = {"type": "invalid_request_error", "message": refusal.message}
            return httpx.Response(400, json={"type": "error", "error": error})
        content = self._answer(body, turns, replayed)
        self.requests.append(RequestRecord(200, thinking, len(replayed)))
        stop = "tool_use" if content[-1]["type"] == "tool_use" else "end_turn"
        usage = {"input_tokens": 20, "output_tokens": 20}
        message: Json = {
            "id": f"msg_{len(self.accepted)}",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
        }
        if body.get("stream"):
            events: list[Json] = [{"type": "message_start", "message": {**message, "content": [], "usage": usage}}]
            for index, block in enumerate(content):
                events += _block_events(index, block)
            events.append({"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 20}})
            events.append({"type": "message_stop"})
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(events))
        return httpx.Response(200, json={**message, "content": content, "stop_reason": stop, "usage": usage})
