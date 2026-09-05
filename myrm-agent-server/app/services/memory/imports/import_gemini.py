"""Google Gemini conversation history and memory export adapter.

[INPUT]
Google Gemini data export payload (Takeout or JSON dump).

Expected payload keys:
  - ``conversations``: list[dict] — conversation sessions or chats
  - ``chats``: list[dict] — alternative key used in direct Gemini exports
  - ``_source``: "gemini" — explicit source identifier

Each Gemini conversation item typically contains:
  - ``title``: str — chat title
  - ``create_time`` or ``created_at`` or ``timestamp``: str | float
  - ``messages`` or ``turns``: list[dict] — messages with author/role and parts/content
  - ``id``: str — conversation ID

[OUTPUT]
MemoryImportDryRunResult mapping Gemini conversations into native episodic memory.

[POS]
Google Gemini competitor import adapter. Converts Google Gemini conversation
and chat export data into episodic memory entries for vector-indexed recall.
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.imports.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
    object_dict,
    text,
)

MAX_PREVIEW_TURNS = 5
MAX_MSG_CHARS = 200


def dry_run_gemini(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Google Gemini export payload into native episodic memory without persisting."""

    conversations = payload.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        conversations = payload.get("chats")

    if not isinstance(conversations, list) or not conversations:
        return build_result(
            source="gemini",
            version="1",
            normalized={},
            mappings=[
                MemoryImportMappingItem(
                    source_bucket="conversations",
                    status="unsupported",
                    item_count=0,
                    reason="No conversations or chats found in payload.",
                ),
            ],
            mapped_items=0,
            unmapped_items=0,
            warnings=["gemini_no_conversations"],
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
        source="gemini",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=0,
        warnings=[],
    )


def is_gemini_payload(payload: dict[str, object]) -> bool:
    """Detect Google Gemini export data by structure or explicit source tag."""

    if payload.get("_source") == "gemini":
        return True
    if "gemini_conversations" in payload or "gemini_chats" in payload:
        return True

    conversations = payload.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        conversations = payload.get("chats")

    if isinstance(conversations, list) and conversations:
        first = conversations[0]
        if isinstance(first, dict):
            if "messages" in first or "turns" in first:
                # Disambiguate from ChatGPT which requires 'mapping' and 'current_node'
                if "mapping" not in first and "current_node" not in first:
                    # Check for Gemini-specific indicators like 'parts' or author 'gemini'/'model'
                    messages = first.get("messages") or first.get("turns")
                    if isinstance(messages, list) and messages:
                        m0 = messages[0]
                        if isinstance(m0, dict) and ("parts" in m0 or m0.get("role") in ("model", "gemini")):
                            return True
    return False


def _parse_conversations(conversations: list[object]) -> list[dict[str, object]]:
    """Convert Gemini conversations into episodic memory entries."""

    items: list[dict[str, object]] = []
    for raw_conv in conversations:
        if not isinstance(raw_conv, dict):
            continue
        conv = object_dict(raw_conv)
        title = text(conv.get("title")) or "Gemini conversation"

        messages = _extract_messages(conv)
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

        raw_time = conv.get("create_time") or conv.get("created_at") or conv.get("timestamp")
        timestamp = _parse_timestamp(raw_time)

        items.append(
            {
                "content": "\n".join(content_parts),
                "event_type": "gemini_conversation",
                "timestamp": timestamp,
                "importance": 0.6,
                "metadata": build_metadata("gemini", conv, ("id", "model", "model_version")),
            }
        )
    return items


def _extract_messages(conv: dict[str, object]) -> list[dict[str, str]]:
    """Extract messages from Gemini conversation turns or messages list."""

    raw_msgs = conv.get("messages") or conv.get("turns")
    if not isinstance(raw_msgs, list):
        return []

    messages: list[dict[str, str]] = []
    for raw_msg in raw_msgs:
        if not isinstance(raw_msg, dict):
            continue
        msg = object_dict(raw_msg)
        author = msg.get("author") or msg.get("role")
        role_str = ""
        if isinstance(author, dict):
            role_str = text(author.get("role") or author.get("name"))
        elif isinstance(author, str):
            role_str = author.strip().lower()

        # Normalize role
        if role_str in ("user", "human"):
            normalized_role = "user"
        elif role_str in ("model", "gemini", "assistant", "ai"):
            normalized_role = "assistant"
        else:
            normalized_role = role_str or "user"

        body = ""
        # Handle Gemini 'parts' list (e.g. [{"text": "..."}, ...])
        parts = msg.get("parts")
        if isinstance(parts, list):
            part_texts = []
            for p in parts:
                if isinstance(p, dict) and "text" in p:
                    part_texts.append(str(p["text"]))
                elif isinstance(p, str):
                    part_texts.append(p)
            body = " ".join(part_texts)
        elif isinstance(msg.get("content"), str):
            body = str(msg["content"])
        elif isinstance(msg.get("text"), str):
            body = str(msg["text"])

        if body.strip():
            messages.append({"role": normalized_role, "content": body.strip()})

    return messages


def _parse_timestamp(val: object) -> str:
    """Parse various timestamp representations to ISO string."""

    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=UTC).isoformat()
        except (OSError, OverflowError, ValueError):
            return iso_or_now(None)
    if isinstance(val, str) and val.strip():
        return iso_or_now(val)
    return iso_or_now(None)
