"""Chat lineage of the memories a pipeline builds from other memories.

[INPUT]
- memory.types::AnyMemory (POS: memory data models)

[OUTPUT]
- chat_links: every chat one memory derives from, the chat it was written from first
- origin_chat_ids: the chats the given memories derive from, the newest memory's chat first

[POS]
A memory written from a chat names that chat in ``source_chat_id``. A memory built from other memories (a merge,
an insight, a deduplication update, a discovered pattern) records the chats of every source, so deleting any one of
those chats reaches it: what a deleted chat contributed must not live on inside a memory it was folded into.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory


def chat_links(memory: AnyMemory) -> list[str]:
    """Each chat the memory derives from once: the chat it was written from, then the chats it was built from.

    A memory without a chat link has none, and a memory kind that carries no lineage list is read by its
    ``source_chat_id`` alone.
    """
    links: dict[str, None] = {}
    if chat_id := getattr(memory, "source_chat_id", None):
        links[chat_id] = None
    links.update(dict.fromkeys(getattr(memory, "source_chat_ids", ())))
    return list(links)


def origin_chat_ids(memories: Iterable[AnyMemory]) -> list[str]:
    """Each chat the memories derive from once, the newest memory's chat first.

    A memory's own chat comes before the chats it was itself built from.
    """
    chats: dict[str, None] = {}
    for memory in sorted(memories, key=lambda m: m.created_at.timestamp(), reverse=True):
        chats.update(dict.fromkeys(chat_links(memory)))
    return list(chats)
