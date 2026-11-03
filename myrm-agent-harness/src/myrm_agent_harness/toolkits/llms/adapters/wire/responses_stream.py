"""Tie the events of one Responses stream together: which function call does an event belong to.

[INPUT]
- collections.abc::Mapping, Sequence (POS: read-only event payloads)

[OUTPUT]
- ResponsesStreamState: per-stream bookkeeping that turns function-call events into chat-completions
  ``tool_calls`` deltas and remembers what the consumer has already been given

[POS]
Inbound leg of the Responses wire. A Responses stream names one function call three ways: the item ``id``
(``fc_…``) on argument deltas, the ``call_id`` (``call_…``) the caller must answer with, and the ``output_index``
position. Every call is announced (``output_item.added``), its arguments arrive as deltas, and the same arguments
come again whole on ``arguments.done``, ``output_item.done`` and ``response.completed``. The consumer concatenates
tool-call deltas by index, so each piece of the arguments must be handed over exactly once and under the call's
own index; this class decides which piece that is. A stream that skips any of these events (arguments only on
``done``, calls only on ``completed``, a bridge that sends the arguments whole on ``added`` and replays them as
deltas) still yields each call's arguments once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

type _Key = tuple[str, str | int]
type ToolCallDelta = dict[str, object]


class _Arguments(Enum):
    NONE = "none"  # nothing handed over yet
    PARTIAL = "partial"  # deltas are being appended
    COMPLETE = "complete"  # the whole string was handed over at once; further copies are replays


@dataclass(slots=True)
class _Call:
    index: int
    named: bool = False
    arguments: _Arguments = _Arguments.NONE


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _identities(item: Mapping[str, object] | None, event: Mapping[str, object]) -> list[_Key]:
    """Every name the payload gives its call, most specific first (position is only a fallback)."""
    keys: list[_Key] = []
    for kind, value in (
        ("item", _text(item.get("id")) if item else ""),
        ("item", _text(event.get("item_id"))),
        ("call", _text(item.get("call_id")) if item else ""),
        ("call", _text(event.get("call_id"))),
    ):
        if value and (kind, value) not in keys:
            keys.append((kind, value))
    return keys


def _position(event: Mapping[str, object]) -> _Key | None:
    index = event.get("output_index")
    return ("out", index) if isinstance(index, int) and not isinstance(index, bool) else None


def _delta(call: _Call, *, call_id: str = "", name: str = "", arguments: str | None = None) -> ToolCallDelta:
    function: dict[str, object] = {}
    if name:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    delta: ToolCallDelta = {"index": call.index, "type": "function", "function": function}
    if call_id:
        delta["id"] = call_id
    return delta


class ResponsesStreamState:
    """Function-call bookkeeping and reasoning flag of one Responses stream (one instance per stream)."""

    __slots__ = ("_by_key", "_calls", "reasoning_streamed")

    def __init__(self) -> None:
        self._calls: list[_Call] = []
        self._by_key: dict[_Key, _Call] = {}
        # Reasoning summary text already handed over as deltas; the closing event must not repeat it.
        self.reasoning_streamed = False

    @property
    def has_calls(self) -> bool:
        """Whether the stream announced any function call (the closing event may not list them)."""
        return bool(self._calls)

    def _resolve(
        self, item: Mapping[str, object] | None, event: Mapping[str, object], *, create: bool
    ) -> tuple[_Call | None, bool]:
        """The call a payload belongs to and whether it was created for it."""
        ids = _identities(item, event)
        position = _position(event)
        keys = [*ids, *([position] if position else [])]
        # A call that carries ids is matched by them alone: servers that report the same position for
        # parallel calls would otherwise merge them.
        found = next((self._by_key[key] for key in (ids or keys) if key in self._by_key), None)
        created = found is None and create and bool(keys)
        if found is None:
            if not created:
                return None, False
            found = _Call(index=len(self._calls))
            self._calls.append(found)
        for key in keys:
            self._by_key.setdefault(key, found)
        return found, created

    def on_item(self, event: Mapping[str, object], item: Mapping[str, object]) -> list[ToolCallDelta]:
        """``output_item.added`` / ``output_item.done`` of a function call."""
        call_id = _text(item.get("call_id")) or _text(item.get("id"))
        name = _text(item.get("name"))
        arguments = _text(item.get("arguments"))
        call, created = self._resolve(item, event, create=bool(call_id and name))
        if call is None:
            return []
        out: list[ToolCallDelta] = []
        announce = created or (not call.named and bool(name))
        if announce:
            call.named = True
        if call.arguments is _Arguments.NONE and arguments:
            call.arguments = _Arguments.COMPLETE
            out.append(
                _delta(call, call_id=call_id if announce else "", name=name if announce else "", arguments=arguments)
            )
        elif announce:
            out.append(_delta(call, call_id=call_id, name=name, arguments=""))
        return out

    def on_arguments(self, event: Mapping[str, object], *, final: bool) -> list[ToolCallDelta]:
        """``function_call_arguments.delta`` (a piece) and ``.done`` (the whole string)."""
        text = _text(event.get("arguments" if final else "delta"))
        call_id = _text(event.get("call_id")) or _text(event.get("item_id"))
        call, created = self._resolve(None, event, create=bool(call_id))
        if call is None or not text:
            return []
        if final:
            if call.arguments is not _Arguments.NONE:
                return []
            call.arguments = _Arguments.COMPLETE
        else:
            if call.arguments is _Arguments.COMPLETE:
                return []
            call.arguments = _Arguments.PARTIAL
        name = _text(event.get("name")) if not call.named else ""
        call.named = call.named or bool(name)
        return [_delta(call, call_id=call_id if created else "", name=name, arguments=text)]

    def on_completed(self, output: Sequence[object]) -> list[ToolCallDelta]:
        """Function calls of the closing ``response.completed``: ids and names for the calls already streamed
        (a call first seen by a delta still carries the item id), whole calls for the ones never streamed."""
        out: list[ToolCallDelta] = []
        for position, item in enumerate(output):
            if not isinstance(item, Mapping) or item.get("type") != "function_call":
                continue
            call_id = _text(item.get("call_id")) or _text(item.get("id"))
            name = _text(item.get("name"))
            if not call_id or not name:
                continue
            call, _ = self._resolve(item, {"output_index": position}, create=True)
            if call is None:
                continue
            if call.arguments is _Arguments.NONE:
                call.arguments = _Arguments.COMPLETE
                # An empty string is a call without parameters; consumers parse the final string as JSON.
                out.append(_delta(call, call_id=call_id, name=name, arguments=_text(item.get("arguments")) or "{}"))
            else:
                out.append(_delta(call, call_id=call_id, name=name))
        return out
