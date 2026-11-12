"""The reply to a memory search that finds nothing.

[INPUT]
- toolkits.memory.agent_surface.memory_recall_budget::{DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT} (POS: the recall limits the reply quotes)
- toolkits.memory.types::MemoryType (POS: memory data models)

[OUTPUT]
- no_result_reply: The zero-hit reply; a search that covers rules adds how stored rules are matched.

[POS]
Shared by memory_search_tool and the MCP memory_recall, so a model that finds no rule learns the same way to look for one on either surface.
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import (
    DEFAULT_RECALL_LIMIT,
    MAX_RECALL_LIMIT,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType

_PLAIN_REPLY = "No relevant memories found."


def no_result_reply(types: Sequence[MemoryType] | None) -> str:
    """Reply for a search over ``types`` (None = every type) that matched nothing.

    A stored rule is matched as one exact phrase, not by meaning, so a natural-language query finds none of them. A
    model that is only told "nothing found" concludes the rule does not exist and saves a duplicate of it.
    """
    if types is not None and MemoryType.PROCEDURAL not in types:
        return _PLAIN_REPLY
    return (
        f"{_PLAIN_REPLY} Stored rules are matched as one exact phrase against their trigger and action: "
        'search one distinctive word, or leave query empty with categories=["rule"] to list rules '
        f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)."
    )
