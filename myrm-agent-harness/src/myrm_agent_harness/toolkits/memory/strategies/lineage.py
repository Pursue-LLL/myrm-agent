"""Chat lineage of the memories a pipeline builds from other memories.

[INPUT]
- memory.types::AnyMemory (POS: memory data models)

[OUTPUT]
- origin_chat_ids: the chats the given memories derive from, the newest memory's chat first

[POS]
A memory written from a chat names that chat in ``source_chat_id``. A memory built from other memories (a merge,
an insight, a deduplication update) records the chats of every source, so deleting any one of those chats reaches
it: what a deleted chat contributed must not live on inside a memory it was folded into.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory


def origin_chat_ids(memories: Iterable[AnyMemory]) -> list[str]:
    """Each chat the memories derive from once, the newest memory's chat first.

    A memory's own chat comes before the chats it was itself built from. Memories without a chat link add nothing,
    and a memory kind that carries no lineage field is read by its ``source_chat_id`` alone.
    """
    chats: dict[str, None] = {}
    for memory in sorted(memories, key=lambda m: m.created_at.timestamp(), reverse=True):
        if chat_id := getattr(memory, "source_chat_id", None):
            chats[chat_id] = None
        chats.update(dict.fromkeys(getattr(memory, "source_chat_ids", ())))
    return list(chats)
