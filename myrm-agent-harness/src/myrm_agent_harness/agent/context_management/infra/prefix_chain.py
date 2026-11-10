"""Digests of a request's messages and the first place two requests differ.

[INPUT]
- langchain_core.messages::BaseMessage (POS: Provider-neutral conversation message.)

[OUTPUT]
- PrefixShift: where a request's message prefix first differs from the previous request's.
- message_digests: one digest per message, blind to cache breakpoints.
- find_prefix_shift: compare two digest chains.

[POS]
Provider prompt caches match a byte-identical prefix. A request that only extends the previous one reuses the
cache; one that edits an earlier message pays full price from that message on. This module names that edit.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import blake2b

from langchain_core.messages import BaseMessage

_DIGEST_BYTES = 12
_FIELD_SEPARATOR = b"\x1f"
# Breakpoints move from message to message as a conversation grows; they are not part of what a message says.
_BREAKPOINT_KEY = "cache_control"


@dataclass(frozen=True, slots=True)
class PrefixShift:
    """The first message whose content differs from the previous request's list.

    ``announced`` is true when the context pipeline said it was rewriting history (compaction, pruning), so the
    shift is expected; an unannounced one is a request that edited an earlier message on its own.
    """

    first_index: int
    previous_length: int
    current_length: int
    announced: bool

    @property
    def truncated(self) -> bool:
        """The request kept every earlier message and dropped the tail."""
        return self.first_index >= self.current_length

    def as_record(self) -> dict[str, object]:
        """JSON-simple form for the cache-metrics log."""
        return {
            "first_index": self.first_index,
            "previous_length": self.previous_length,
            "current_length": self.current_length,
            "kind": "truncated" if self.truncated else "rewritten",
            "announced": self.announced,
        }


def _without_breakpoint(mapping: Mapping[str, object]) -> dict[str, object]:
    return {key: item for key, item in mapping.items() if key != _BREAKPOINT_KEY}


def _canonical(value: object) -> bytes:
    """Stable bytes for a content block, a tool-call list or an extras mapping."""
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    if isinstance(value, Mapping):
        value = _without_breakpoint(value)
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", "surrogatepass")
    except (TypeError, ValueError):
        # Mixed-type keys or a cycle: the digest must still exist, so fall back to the object's own text.
        return repr(value).encode("utf-8", "surrogatepass")


def _message_digest(message: BaseMessage) -> str:
    hasher = blake2b(digest_size=_DIGEST_BYTES)
    hasher.update(message.type.encode())
    content = message.content
    for block in content if isinstance(content, list) else (content,):
        hasher.update(_FIELD_SEPARATOR)
        hasher.update(_canonical(block))
    # Fields that reach the wire next to the content; falsy ones are absent from the request too.
    for extra in (
        getattr(message, "tool_calls", None),
        getattr(message, "tool_call_id", None),
        message.name,
        _without_breakpoint(message.additional_kwargs),
    ):
        if extra:
            hasher.update(_FIELD_SEPARATOR)
            hasher.update(_canonical(extra))
    return hasher.hexdigest()


def message_digests(messages: Sequence[BaseMessage]) -> tuple[str, ...]:
    """One digest per message; two requests share a cacheable prefix exactly as far as their digests agree."""
    return tuple(_message_digest(message) for message in messages)


def find_prefix_shift(previous: Sequence[str], current: Sequence[str], *, announced: bool) -> PrefixShift | None:
    """Where ``current`` stops being an extension of ``previous``; None when it only appends (or repeats)."""
    shared = min(len(previous), len(current))
    for index in range(shared):
        if previous[index] != current[index]:
            return PrefixShift(index, len(previous), len(current), announced)
    if len(current) < len(previous):
        return PrefixShift(len(current), len(previous), len(current), announced)
    return None
