"""Wiki vault lifecycle and shared archiver access.

[INPUT]
- app.services.wiki.vault_resolver::resolve_wiki_vault_path (POS: wiki filesystem SSOT)
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving service)
- myrm_agent_harness.toolkits.wiki::WikiStructure (POS: Wiki file system abstraction layer)

[OUTPUT]
- init_wiki_vault_at_startup(): migrate legacy paths and ensure directory layout
- get_wiki_archiver(): process-scoped archiver for API and background hooks

[POS]
Application-level wiki vault bootstrap and shared service accessor.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.wiki import WikiStructure

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault_resolver import (
    migrate_legacy_wiki_vaults,
    resolve_agent_wiki_vault_path,
    resolve_wiki_vault_path,
    sanitize_wiki_scope_id,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger(__name__)

_archiver: MemoryToWikiArchiver | None = None
_archiver_cache_key: tuple[int, str, int] | None = None


async def init_wiki_vault_at_startup() -> None:
    """Migrate legacy wiki directories and ensure Karpathy layout exists."""
    result = migrate_legacy_wiki_vaults()
    vault_path = resolve_agent_wiki_vault_path("default")
    WikiStructure(vault_path).ensure_structure()
    if result.skipped:
        logger.debug("Wiki vault ready at %s (migration already applied)", vault_path)
    else:
        logger.info(
            "Wiki vault initialized at %s (legacy_files=%d)",
            vault_path,
            result.files_copied,
        )


def get_wiki_archiver(
    llm: BaseChatModel,
    manager: MemoryManager | None = None,
    agent_id: str | None = None,
) -> MemoryToWikiArchiver:
    """Return a process-scoped archiver bound to an agent wiki vault path."""
    global _archiver, _archiver_cache_key

    manager_key = id(manager) if manager is not None else 0
    cache_key = (id(llm), sanitize_wiki_scope_id(agent_id), manager_key)
    if _archiver is None or _archiver_cache_key != cache_key:
        _archiver = MemoryToWikiArchiver(
            llm,
            wiki_dir=resolve_wiki_vault_path(agent_id),
            manager=manager,
        )
        _archiver_cache_key = cache_key
    return _archiver


def reset_wiki_archiver_cache_for_tests() -> None:
    """Clear cached archiver (tests only)."""
    global _archiver, _archiver_cache_key
    _archiver = None
    _archiver_cache_key = None
