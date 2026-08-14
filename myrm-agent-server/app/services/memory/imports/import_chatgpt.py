"""ChatGPT conversation history import adapter.

[INPUT]
ChatGPT data export payload (conversations.json or ZIP containing it).

Expected payload keys (populated by frontend upload):
  - ``conversations``: list[dict] — conversation objects with tree-based mapping
  - ``_source``: "chatgpt" — source identifier

Each conversation object follows ChatGPT's standard export format:
  - ``title``: str — conversation title
  - ``create_time``: float — unix timestamp
  - ``mapping``: dict[str, node] — tree of message nodes
  - ``current_node``: str — leaf node ID for traversal
  - ``id``: str — unique conversation ID (used for dedup)

[OUTPUT]
MemoryImportDryRunResult mapping ChatGPT conversations to native episodic bucket.

[POS]
ChatGPT competitor import adapter. Converts ChatGPT's tree-based conversation
data into episodic memory entries for vector-indexed recall.
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
    object_dict,
    text,
)

MAX_PREVIEW_TURNS = 5
MAX_MSG_CHARS = 200


def dry_run_chatgpt(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a ChatGPT export payload into native episodic memory without persisting."""

    conversations = payload.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        return build_result(
            source="chatgpt",
            version="1",
            normalized={},
            mappings=[
                MemoryImportMappingItem(
                    source_bucket="conversations",
                    status="unsupported",
                    item_count=0,
                    reason="No conversations found in payload.",
                ),
            ],
            mapped_items=0,
            unmapped_items=0,
            warnings=["chatgpt_no_conversations"],
        )

    episodic_items = _parse_conversations(conversations)
    mapped_items = len(episodic_items)

    normalized: dict[str, list[dict[str, object]]] = {}
    if episodic_items:
        normalized["episodic"] = episodic_items

    mappings = [
        MemoryImportMappingItem(
            source_bucket="conversations",
            target_bucket="episodic",
            status="mapped" if episodic_items else "unsupported",
            item_count=len(conversations),
            imported_count=mapped_items,
            reason="" if episodic_items else "No valid conversations parsed.",
        ),
    ]

    return build_result(
        source="chatgpt",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=0,
        warnings=[],
    )


def is_chatgpt_payload(payload: dict[str, object]) -> bool:
    """Detect ChatGPT export data by structure or explicit source tag."""

    if payload.get("_source") == "chatgpt":
        return True
    conversations = payload.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        return False
    first = conversations[0] if conversations else None
    if isinstance(first, dict):
        return "mapping" in first and "current_node" in first
    return False


def _parse_conversations(conversations: list[object]) -> list[dict[str, object]]:
    """Convert ChatGPT conversations into episodic memory entries."""

    items: list[dict[str, object]] = []
    for raw_conv in conversations:
        if not isinstance(raw_conv, dict):
            continue
        conv = object_dict(raw_conv)
        title = text(conv.get("title")) or "ChatGPT conversation"

        messages = _extract_messages_from_mapping(conv)
        content_parts = [title]
        if messages:
            msg_previews = []
            for msg in messages[:MAX_PREVIEW_TURNS]:
                role = msg.get("role", "")
                body = msg.get("content", "")
                if role and body:
                    msg_previews.append(f"{role}: {body[:MAX_MSG_CHARS]}")
            if msg_previews:
                content_parts.append(" | ".join(msg_previews))

        create_time = conv.get("create_time")
        timestamp = _unix_to_iso(create_time) if isinstance(create_time, int | float) else iso_or_now(None)

        items.append(
            {
                "content": "\n".join(content_parts),
                "event_type": "chatgpt_conversation",
                "timestamp": timestamp,
                "importance": 0.6,
                "metadata": build_metadata("chatgpt", conv, ("id", "model_slug")),
            }
        )
    return items


def _extract_messages_from_mapping(conv: dict[str, object]) -> list[dict[str, str]]:
    """Walk the tree mapping from current_node backwards to extract messages."""

    mapping = conv.get("mapping")
    if not isinstance(mapping, dict):
        return []

    current_node = conv.get("current_node")
    if not isinstance(current_node, str):
        return []

    messages: list[dict[str, str]] = []
    visited: set[str] = set()

    while current_node and current_node not in visited:
        visited.add(current_node)
        node = mapping.get(current_node)
        if not isinstance(node, dict):
            break

        message = node.get("message")
        if isinstance(message, dict):
            author = message.get("author")
            role = ""
            if isinstance(author, dict):
                role = text(author.get("role"))
            elif isinstance(message.get("role"), str):
                role = text(message.get("role"))

            if role in ("user", "assistant"):
                content = message.get("content")
                body = ""
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        body = " ".join(str(p) for p in parts if isinstance(p, str))
                if body:
                    messages.append({"role": role, "content": body})

        parent = node.get("parent")
        current_node = parent if isinstance(parent, str) else None

    messages.reverse()
    return messages


def _unix_to_iso(ts: int | float) -> str:
    """Convert a UNIX timestamp to ISO format string."""

    try:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return datetime.now(UTC).isoformat()
