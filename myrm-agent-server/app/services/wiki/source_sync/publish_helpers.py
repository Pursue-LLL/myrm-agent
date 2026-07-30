"""Shared publish_raw helpers for wiki source sync.

[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.raw_gate::publish_raw (POS: raw publication gate)

[OUTPUT]
- publish_source_markdown / build_frontmatter / sanitize_path_segment helpers

[POS]
Shared zero-LLM publish helpers for Gmail/RSS/integration mirror ingest paths.
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
    RawConflictPolicy,
    RawPublishRequest,
    RawPublishResult,
    publish_raw,
)

logger = logging.getLogger(__name__)


async def publish_source_markdown(
    structure: WikiStructure,
    *,
    relative_path: str,
    content: str,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> RawPublishResult:
    result = await publish_raw(
        structure,
        RawPublishRequest(
            relative_path=relative_path,
            content=content,
            conflict_policy=RawConflictPolicy.SKIP,
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
    lines = ["---", f'source: "{source}"', f'title: "{title.replace(chr(34), chr(39))}"']
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
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    return cleaned[:120] or "item"
