"""The reply to a memory search that finds nothing.

[INPUT]
- toolkits.memory.agent_surface.memory_recall_budget::{DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT} (POS: the recall limits the reply quotes)
- toolkits.memory.types::MemoryType (POS: memory data models)

[OUTPUT]
- no_result_reply: The zero-hit reply; a search that covers rules adds how stored rules are matched, and one run under an explicit since/until window names that save-time window.

[POS]
Shared by memory_search_tool and the MCP memory_recall, so a model that finds no rule, or nothing inside a time window, learns the same way to look again on either surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import (
    DEFAULT_RECALL_LIMIT,
    MAX_RECALL_LIMIT,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType

_PLAIN_REPLY = "No relevant memories found."

_RULES_NOTE = (
    "Stored rules are matched as one exact phrase against their trigger and action: "
    'search one distinctive word, or leave query empty with categories=["rule"] to list rules '
    f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)."
)

# The memory types whose search reads since/until. Rule and profile searches ignore both bounds, so a window never
# explains why one of those found nothing.
_TIME_FILTERED_TYPES = frozenset({MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.CONVERSATION})


def no_result_reply(
    types: Sequence[MemoryType] | None,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> str:
    """Reply for a search over ``types`` (None = every type) that matched nothing.

    A stored rule is matched as one exact phrase, not by meaning, so a natural-language query finds none of them. A
    model that is only told "nothing found" concludes the rule does not exist and saves a duplicate of it.

    ``since`` and ``until`` are the explicit bounds the search ran under. They match when a memory was saved, so a
    memory saved outside them is invisible to the search; a model that is not told the window concludes the memory
    does not exist.
    """
    parts = [_PLAIN_REPLY]
    window_note = _window_note(types, since, until)
    if window_note is not None:
        parts.append(window_note)
    if types is None or MemoryType.PROCEDURAL in types:
        parts.append(_RULES_NOTE)
    return " ".join(parts)


def _window_note(types: Sequence[MemoryType] | None, since: datetime | None, until: datetime | None) -> str | None:
    """Names the save-time window a search ran under; None when it had no bound or read none of its types."""
    if types is not None and _TIME_FILTERED_TYPES.isdisjoint(types):
        return None
    bounds = [
        f"{word} {bound.astimezone(UTC).strftime('%Y-%m-%d %H:%M')} UTC"
        for word, bound in (("after", since), ("before", until))
        if bound is not None
    ]
    if not bounds:
        return None
    return (
        f"This search was limited to memories saved {' and '.join(bounds)}: since/until match when a memory was saved, "
        "not the date it describes. If the memory may have been saved outside this period, retry without since/until."
    )
