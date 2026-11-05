"""[INPUT]
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: wiki vault layout)
- app.services.wiki.vault::resolve_wiki_vault_path (POS: per-agent wiki vault root)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _wiki_concept_part / _wiki_raw_file_part: read one wiki page or raw source
- wiki_concept_part / wiki_raw_file_part: @wiki: handlers

[POS]
Wiki @ references. Concept pages and raw source files are two different lookups over the same vault,
so they share a module but keep separate handlers.
"""

from __future__ import annotations

import logging

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _can_inline, _format_size, _xml_error, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)


async def _wiki_concept_part(
    concept_name: str,
    current_total_bytes: int,
    agent_id: str | None = None,
) -> tuple[str, int]:
    """Read a wiki concept by name and build an XML context part."""
    try:
        from myrm_agent_harness.toolkits.wiki import WikiStructure

        from app.services.wiki.vault import resolve_wiki_vault_path

        vault_path = resolve_wiki_vault_path(agent_id)
        structure = WikiStructure(vault_path)
        concept_path = structure.resolve_concept_file_path(concept_name)
        if concept_path is None or not concept_path.exists():
            return _xml_error(f"@wiki:{concept_name}", "concept not found"), 0

        content = concept_path.read_text(encoding="utf-8")
        content_bytes = len(content.encode("utf-8"))
        if _can_inline(content_bytes, current_total_bytes):
            return (
                _xml_part(f"@wiki:{concept_name}", "wiki-concept", content),
                content_bytes,
            )
        return (
            _xml_metadata(
                f"@wiki:{concept_name}",
                "wiki-concept",
                f"Concept too large ({_format_size(content_bytes)})",
            ),
            0,
        )
    except Exception as e:
        logger.warning("Failed to read wiki concept %s: %s", concept_name, e)
        return _xml_error(f"@wiki:{concept_name}", "read failed"), 0


async def _wiki_raw_file_part(
    file_id: str,
    display: str,
    current_total_bytes: int,
    agent_id: str | None = None,
) -> tuple[str, int]:
    """Read a wiki raw file and build an XML context part."""
    try:
        from myrm_agent_harness.toolkits.wiki import WikiStructure

        from app.services.wiki.vault import resolve_wiki_vault_path

        vault_path = resolve_wiki_vault_path(agent_id)
        structure = WikiStructure(vault_path)
        raw_path = structure.raw_dir / file_id
        if not raw_path.exists():
            return _xml_error(display, "raw file not found"), 0

        content = raw_path.read_text(encoding="utf-8", errors="replace")
        content_bytes = len(content.encode("utf-8"))
        if _can_inline(content_bytes, current_total_bytes):
            return _xml_part(display, "wiki-raw-file", content), content_bytes
        return (
            _xml_metadata(
                display,
                "wiki-raw-file",
                f"File too large ({_format_size(content_bytes)})",
            ),
            0,
        )
    except Exception as e:
        logger.warning("Failed to read wiki raw file %s: %s", file_id, e)
        return _xml_error(display, "read failed"), 0


async def wiki_concept_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    concept_name = ref.concept_name or ref.label or ""
    if not concept_name:
        ctx.parts.append(_xml_error("@wiki", "missing concept_name"))
        return
    part, consumed_bytes = await _wiki_concept_part(concept_name, ctx.total_bytes, ctx.agent_id)
    ctx.parts.append(part)
    ctx.total_bytes += consumed_bytes


async def wiki_raw_file_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    file_id = ref.file_id or ref.path or ""
    display = ref.label or file_id
    if not file_id:
        ctx.parts.append(_xml_error(display, "missing file_id or path"))
        return
    part, consumed_bytes = await _wiki_raw_file_part(file_id, display, ctx.total_bytes, ctx.agent_id)
    ctx.parts.append(part)
    ctx.total_bytes += consumed_bytes
