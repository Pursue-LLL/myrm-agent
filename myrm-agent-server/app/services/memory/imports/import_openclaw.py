"""OpenClaw memory import adapter.

[INPUT]
OpenClaw data payload with session-based memories and structured memory entries.

Expected payload keys (populated by source_discovery or frontend upload):
  - ``openclaw_sessions``: list[dict] — conversation sessions with messages
  - ``openclaw_memory``: list[dict] — structured memory entries (incl. workspace MEMORY/USER.md via loader)
  - ``openclaw_skills``: list[dict] — skill definitions (routed to skill migration)
  - ``_source``: "openclaw" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping OpenClaw data to native semantic/episodic buckets.

[POS]
OpenClaw competitor import adapter. Converts OpenClaw's session-based and
structured memory data into native MyrmAgent memory format.
"""

from __future__ import annotations

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


def dry_run_openclaw(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map an OpenClaw data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    sessions = payload.get("openclaw_sessions")
    if isinstance(sessions, list) and sessions:
        episodic_items = _parse_sessions(sessions)
        if episodic_items:
            normalized["episodic"] = episodic_items
            mapped_items += len(episodic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="openclaw_sessions",
                target_bucket="episodic",
                status="mapped" if episodic_items else "unsupported",
                item_count=len(sessions),
                imported_count=len(episodic_items),
                reason="" if episodic_items else "No valid sessions found.",
            )
        )

    memory_entries = payload.get("openclaw_memory")
    if isinstance(memory_entries, list) and memory_entries:
        semantic_items = _parse_memory_entries(memory_entries)
        if semantic_items:
            normalized.setdefault("semantic", []).extend(semantic_items)
            mapped_items += len(semantic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="openclaw_memory",
                target_bucket="semantic",
                status="mapped" if semantic_items else "unsupported",
                item_count=len(memory_entries),
                imported_count=len(semantic_items),
                reason="" if semantic_items else "No valid memory entries found.",
            )
        )

    skills = payload.get("openclaw_skills")
    if isinstance(skills, list) and skills:
        unmapped_items += len(skills)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="openclaw_skills",
                status="unsupported",
                item_count=len(skills),
                unmapped_count=len(skills),
                reason="Skills are migrated through the skill migration review pipeline, not the memory import path.",
            )
        )
        warnings.append("openclaw_skills_detected")

    return build_result(
        source="openclaw",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _parse_sessions(sessions: list[object]) -> list[dict[str, object]]:
    """Convert OpenClaw session data into episodic memory items."""

    items: list[dict[str, object]] = []
    for raw_session in sessions:
        if not isinstance(raw_session, dict):
            continue
        session = object_dict(raw_session)
        title = text(session.get("title")) or text(session.get("name")) or "OpenClaw session"
        messages = session.get("messages")
        summary = text(session.get("summary"))

        content_parts = [title]
        if summary:
            content_parts.append(summary)
        elif isinstance(messages, list):
            msg_texts = []
            for msg in messages[:5]:
                if isinstance(msg, dict):
                    msg_text = text(object_dict(msg).get("content"))
                    if msg_text:
                        msg_texts.append(msg_text[:200])
            if msg_texts:
                content_parts.append(" | ".join(msg_texts))

        items.append(
            {
                "content": "\n".join(content_parts),
                "event_type": "openclaw_session",
                "timestamp": iso_or_now(session.get("created_at") or session.get("createdAt")),
                "importance": 0.6,
                "metadata": build_metadata("openclaw", session, ("id", "model", "provider")),
            }
        )
    return items


def _parse_memory_entries(entries: list[object]) -> list[dict[str, object]]:
    """Convert OpenClaw structured memory entries into semantic memory items."""

    items: list[dict[str, object]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = object_dict(raw_entry)
        content = text(entry.get("content")) or text(entry.get("fact")) or text(entry.get("value"))
        if not content:
            continue
        items.append(
            {
                "content": content,
                "importance": 0.7,
                "confidence": 0.75,
                "tags": ["openclaw_memory"],
                "created_at": iso_or_now(entry.get("created_at") or entry.get("createdAt")),
                "metadata": build_metadata("openclaw", entry, ("id", "type", "category")),
            }
        )
    return items
