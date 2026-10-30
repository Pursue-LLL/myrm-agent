"""Build zero-LLM hot.md snapshot content from vault state.

[INPUT]
- ..core.structure::WikiStructure (POS: Wiki file system abstraction layer)
- ..core.frontmatter_contract::read_published_text (POS: published-page reader, the publish_status gate)
- ..core.link_resolver::concept_link_name (POS: vault-relative page name)

[OUTPUT]
- HotSnapshot: immutable hot.md section data
- build_hot_snapshot: derive snapshot from vault filesystem state
- render_hot_markdown: render the three-section hot.md body

[POS]
Hot cache snapshot builder. Derives recent ops, key pages, and open questions without LLM calls. Key pages are
published pages only: the snapshot prefixes every `wiki_query` answer, which must not name a page retrieval refuses to
return.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import read_published_text
from myrm_agent_harness.toolkits.wiki.core.link_resolver import concept_link_name
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

_KEY_PAGE_LIMIT = 5


@dataclass(frozen=True, slots=True)
class HotSnapshot:
    recent_ops: tuple[str, ...]
    key_pages: tuple[tuple[str, str], ...]
    open_questions: tuple[str, ...]


def _read_metadata_concept_count(metadata_path: Path) -> int | None:
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        total = payload.get("total_concepts")
        return int(total) if isinstance(total, int) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def build_hot_snapshot(
    structure: WikiStructure,
    *,
    last_event_summary: str,
    pending_count: int = 0,
    queue_pending: int = 0,
) -> HotSnapshot:
    """Derive hot cache sections from vault filesystem state (no LLM)."""
    concept_paths = structure.list_concepts()
    concept_count = len(concept_paths)
    metadata_count = _read_metadata_concept_count(structure.get_wiki_metadata_path())
    if metadata_count is not None:
        concept_count = metadata_count

    recent_ops: list[str] = [last_event_summary]
    if queue_pending > 0:
        recent_ops.append(f"Ingestion queue: {queue_pending} file(s) pending compilation")
    if pending_count > 0:
        recent_ops.append(f"HITL pending edits: {pending_count} awaiting review")

    key_pages: list[tuple[str, str]] = []
    for path in concept_paths:
        if len(key_pages) == _KEY_PAGE_LIMIT:
            break
        if read_published_text(path) is not None:
            key_pages.append((concept_link_name(path, structure.concepts_dir), "Indexed concept page"))

    open_questions: list[str] = []
    if pending_count > 0:
        open_questions.append("Review pending wiki edits in Settings → Wiki")
    if queue_pending > 0:
        open_questions.append("Wait for compile queue to finish or run Compile")
    if concept_count == 0:
        open_questions.append("Import or ingest sources to seed the wiki vault")

    if not open_questions:
        open_questions.append("Run Maintain periodically to keep links and types healthy")

    return HotSnapshot(
        recent_ops=tuple(recent_ops[:6]),
        key_pages=tuple(key_pages),
        open_questions=tuple(open_questions[:4]),
    )


def render_hot_markdown(snapshot: HotSnapshot) -> str:
    """Render the three-section hot.md body."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Recent context",
        "",
        f"> Last updated: {timestamp}",
        "",
        "## Recent operations",
    ]
    for item in snapshot.recent_ops:
        lines.append(f"- {item}")
    lines.extend(["", "## Key pages"])
    for name, reason in snapshot.key_pages:
        lines.append(f"- [[{name}]] — {reason}")
    lines.extend(["", "## Open questions"])
    for question in snapshot.open_questions:
        lines.append(f"- {question}")
    lines.append("")
    return "\n".join(lines)
