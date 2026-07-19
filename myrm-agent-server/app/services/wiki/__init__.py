"""Wiki services for myrm-agent-server business layer.

[INPUT]
- .memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving)
- .vault_resolver (POS: Wiki vault path resolution and legacy migration)
- .vault_service (POS: Wiki archiver singleton lifecycle management)

[OUTPUT]
- Public re-exports for all wiki service symbols
"""

from .memory_to_wiki import MemoryToWikiArchiver
from .vault_resolver import (
    is_agent_layout_migration_complete,
    is_legacy_migration_complete,
    is_vault_ready,
    list_legacy_wiki_vault_paths,
    migrate_global_wiki_to_agent_layout,
    migrate_legacy_wiki_vaults,
    resolve_agent_wiki_vault_path,
    resolve_shared_wiki_vault_path,
    resolve_shared_wiki_vault_paths,
    resolve_wiki_vault_layout,
    resolve_wiki_vault_path,
    sanitize_wiki_scope_id,
)
from .vault_service import get_wiki_archiver, init_wiki_vault_at_startup, reset_wiki_archiver_cache_for_tests

__all__ = [
    "MemoryToWikiArchiver",
    "get_wiki_archiver",
    "init_wiki_vault_at_startup",
    "is_agent_layout_migration_complete",
    "is_legacy_migration_complete",
    "is_vault_ready",
    "list_legacy_wiki_vault_paths",
    "migrate_global_wiki_to_agent_layout",
    "migrate_legacy_wiki_vaults",
    "reset_wiki_archiver_cache_for_tests",
    "resolve_agent_wiki_vault_path",
    "resolve_shared_wiki_vault_path",
    "resolve_shared_wiki_vault_paths",
    "resolve_wiki_vault_layout",
    "resolve_wiki_vault_path",
    "sanitize_wiki_scope_id",
]
