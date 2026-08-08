"""Schedule wiki vault git snapshots for server-side mutation hooks.

[INPUT]
app.services.wiki.memory_to_wiki::MemoryToWikiArchiver

[OUTPUT]
schedule_wiki_vault_git_snapshot: Non-blocking git commit when version control is enabled

[POS]
Server bridge for vault mutation SSOT: structural cache invalidation + async git snapshot.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


async def schedule_wiki_vault_git_snapshot(archiver: MemoryToWikiArchiver, reason: str) -> None:
    """Run vault git snapshot on a worker thread; never raises to callers."""
    try:
        result = await asyncio.to_thread(archiver.commit_vault_git, reason)
        if result.committed:
            logger.info("Wiki vault git snapshot (%s): %s", reason, result.commit_hash)
    except Exception as exc:
        logger.warning("Wiki vault git snapshot skipped (%s): %s", reason, exc)


async def after_wiki_vault_mutation(archiver: MemoryToWikiArchiver, reason: str) -> None:
    """Invalidate structural stats cache and schedule a vault git snapshot."""
    from app.services.wiki.structural_stats_cache import invalidate_structural_lint_cache

    invalidate_structural_lint_cache(archiver._structure)
    await schedule_wiki_vault_git_snapshot(archiver, reason)
