"""Mirror Integration Memory new items into wiki raw.

[INPUT]
- myrm_agent_harness.toolkits.memory.integration.types::IntegrationSyncResult (POS: integration pull results)

[OUTPUT]
- mirror_integration_sync_results_to_wiki: publish integration items to wiki raw/

[POS]
Bridge integration memory sync output into wiki raw ingest pipeline.
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory.integration.types import IntegrationSyncResult

from app.services.wiki.source_sync.publish_helpers import build_frontmatter, publish_source_markdown, sanitize_path_segment
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult

logger = logging.getLogger(__name__)


async def mirror_integration_sync_results_to_wiki(
    results: list[IntegrationSyncResult],
    *,
    llm: BaseChatModel | None,
    agent_id: str | None,
    auto_compile: bool,
) -> WikiSourceSyncResult:
    summary = WikiSourceSyncResult(source="integrations")
    if llm is None:
        return summary

    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    structure = archiver._structure
    compiler = archiver._compiler

    for sync_result in results:
        provider = sanitize_path_segment(sync_result.provider.replace("mcp:", ""))
        for item in sync_result.new_items:
            title = item.get("title") or item.get("type") or "integration"
            text = item.get("text") or item.get("content") or ""
            external_id = item.get("external_object_id") or item.get("external_id") or title
            if not str(text).strip():
                summary.skipped += 1
                continue
            safe_id = sanitize_path_segment(str(external_id))
            relative_path = f"integrations/{provider}/{safe_id}.md"
            frontmatter = build_frontmatter(
                source="integration",
                title=str(title),
                external_id=str(external_id),
                extra={"provider": sync_result.provider},
            )
            content = frontmatter + f"# {title}\n\n{text}\n"
            try:
                publish = await publish_source_markdown(
                    structure,
                    relative_path=relative_path,
                    content=content,
                    auto_compile=auto_compile,
                    compiler_enqueue=compiler,
                )
                if publish.written:
                    summary.published += 1
                elif publish.conflict_skipped or publish.skipped:
                    summary.skipped += 1
                elif publish.security_blocked:
                    summary.failed += 1
                else:
                    summary.skipped += 1
            except Exception as exc:
                logger.warning("Integration mirror failed: %s", exc)
                summary.failed += 1
                summary.errors.append(str(exc))

    return summary
