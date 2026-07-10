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
    is_legacy_migration_complete,
    is_vault_ready,
    list_legacy_wiki_vault_paths,
    migrate_legacy_wiki_vaults,
    resolve_wiki_vault_path,
)
from .vault_service import get_wiki_archiver, init_wiki_vault_at_startup, reset_wiki_archiver_cache_for_tests

__all__ = [
    "MemoryToWikiArchiver",
    "get_wiki_archiver",
    "init_wiki_vault_at_startup",
    "is_legacy_migration_complete",
    "is_vault_ready",
    "list_legacy_wiki_vault_paths",
    "migrate_legacy_wiki_vaults",
    "reset_wiki_archiver_cache_for_tests",
    "resolve_wiki_vault_path",
]
