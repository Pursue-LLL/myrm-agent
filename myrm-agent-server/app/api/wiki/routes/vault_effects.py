"""[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map::WikiCognitiveMapService / WikiMapEvent / WikiMapEventType (POS: OKF 认知地图模块入口。提供 wiki/index.md, wiki/log.md, wiki/hot.md 与 wiki/SCHEMA.md 的确定性免 LLM 构建与刷新。)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian /)

[OUTPUT]
- _refresh_wiki_cognitive_map: Rebuild OKF index/log/hot after a wiki lifecycle event.
- _after_wiki_vault_mutation: Drop stats cache and commit vault git snapshot after wiki mutations.

[POS]
所有写 wiki 的路由在落盘后调用，保证索引、热区与认知地图与磁盘一致。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiCognitiveMapService,
    WikiMapEvent,
    WikiMapEventType,
)

from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


def _refresh_wiki_cognitive_map(
    archiver: MemoryToWikiArchiver,
    event_type: WikiMapEventType,
    summary: str,
    details: dict[str, object] | None = None,
) -> None:
    """Rebuild OKF index/log/hot after a wiki lifecycle event."""
    pending_stats = archiver._pending_mgr.get_stats()
    queue_stats = archiver._queue.get_stats()
    WikiCognitiveMapService(
        archiver._structure,
        get_pending_count=lambda: int(pending_stats.get("pending", 0)),
        get_queue_pending=lambda: int(queue_stats.get("pending", 0)),
    ).refresh(
        WikiMapEvent(
            event_type=event_type,
            summary=summary,
            details=details or {},
        )
    )


async def _after_wiki_vault_mutation(archiver: MemoryToWikiArchiver, reason: str) -> None:
    """Drop stats cache and commit vault git snapshot after wiki mutations."""
    from app.services.wiki.vault import after_wiki_vault_mutation

    await after_wiki_vault_mutation(archiver, reason)
