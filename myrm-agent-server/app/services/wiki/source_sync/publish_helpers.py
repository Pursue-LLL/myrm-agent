"""Shared publish_raw helpers for wiki source sync.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.raw_gate::publish_raw (POS: raw publication gate)

[OUTPUT]
- publish_source_markdown / build_frontmatter / sanitize_path_segment helpers
- RawConflictPolicy: re-exported so connectors choose SKIP (immutable) or SUPERSEDE (versioned source)

[POS]
Shared zero-LLM publish helpers for Feishu/Gmail/GDrive/RSS/Zotero/integration mirror ingest paths.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
    RawConflictPolicy,
    RawPublishRequest,
    RawPublishResult,
    publish_raw,
)

logger = logging.getLogger(__name__)

_MAX_SEGMENT_CHARS = 120
# Linux NAME_MAX is 255 bytes; the budget leaves room for the ``-<id>.md`` suffix callers append.
_MAX_SEGMENT_BYTES = 200

__all__ = ["RawConflictPolicy", "build_frontmatter", "publish_source_markdown", "sanitize_path_segment"]


async def publish_source_markdown(
    structure: WikiStructure,
    *,
    relative_path: str,
    content: str,
    auto_compile: bool,
    compiler_enqueue: object | None,
    conflict_policy: RawConflictPolicy = RawConflictPolicy.SKIP,
    supersede_reason: str = "",
) -> RawPublishResult:
    """Publish *content* as a raw source; ``SUPERSEDE`` requires a non-empty *supersede_reason*."""
    result = await publish_raw(
        structure,
        RawPublishRequest(
            relative_path=relative_path,
            content=content,
            conflict_policy=conflict_policy,
            supersede_reason=supersede_reason,
        ),
        caller="settings",
    )
    if result.written and auto_compile and compiler_enqueue is not None:
        enqueue = getattr(compiler_enqueue, "enqueue_file", None)
        if callable(enqueue):
            enqueue(result.absolute_path)
    return result


def build_frontmatter(
    *,
    source: str,
    title: str,
    external_id: str,
    extra: dict[str, str] | None = None,
) -> str:
    lines = [
        "---",
        f'source: "{source}"',
        f'title: "{title.replace(chr(34), chr(39))}"',
    ]
    if external_id:
        lines.append(f'external_id: "{external_id}"')
    if extra:
        for key, value in extra.items():
            safe = value.replace('"', "'")
            lines.append(f'{key}: "{safe}"')
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def sanitize_path_segment(value: str) -> str:
    """Return a filesystem-safe segment bounded by both character and UTF-8 byte budgets."""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())[:_MAX_SEGMENT_CHARS]
    encoded = cleaned.encode()
    if len(encoded) > _MAX_SEGMENT_BYTES:
        cleaned = encoded[:_MAX_SEGMENT_BYTES].decode(errors="ignore")
    return cleaned or "item"
