"""Wiki vault domain — path SSOT, lifecycle, export, and git hooks.

[INPUT]
- app.services.wiki.vault.resolver (POS: wiki filesystem layout SSOT)
- app.services.wiki.vault.service (POS: startup lifecycle + shared archiver)
- app.services.wiki.vault.export (POS: portable vault ZIP packager)
- app.services.wiki.vault.git_snapshot / git_status (POS: vault git hooks)

[OUTPUT]
- Public vault facade re-exports (resolver + service + export + git)
- WikiVaultMigrationResult / WikiAgentLayoutMigrationResult / WikiVaultSeedResult

[POS]
Domain subpackage for everything wiki vault related. Facade module name
``app.services.wiki.vault`` aggregates resolver / service / export / git hooks;
internal implementation lives in ``resolver.py`` / ``service.py`` /
``export.py`` / ``git_snapshot.py`` / ``git_status.py``.
"""

from __future__ import annotations

from app.services.wiki.vault.export import build_wiki_export_zip
from app.services.wiki.vault.git_snapshot import after_wiki_vault_mutation
from app.services.wiki.vault.git_status import VaultGitStatus, read_vault_git_status
from app.services.wiki.vault.resolver import (
    WikiAgentLayoutMigrationResult,
    WikiVaultMigrationResult,
    WikiVaultSeedResult,
    is_agent_layout_migration_complete,
    is_legacy_migration_complete,
    is_vault_ready,
    list_legacy_wiki_vault_paths,
    migrate_global_wiki_to_agent_layout,
    migrate_legacy_wiki_vaults,
    resolve_agent_wiki_vault_path,
    resolve_shared_wiki_vault_labels,
    resolve_shared_wiki_vault_path,
    resolve_shared_wiki_vault_paths,
    resolve_wiki_vault_layout,
    resolve_wiki_vault_path,
    sanitize_wiki_scope_id,
    seed_agent_vault_from_default,
    vault_has_wiki_content,
    wiki_root,
)
from app.services.wiki.vault.service import (
    get_wiki_archiver,
    init_wiki_vault_at_startup,
    reset_wiki_archiver_cache_for_tests,
)

__all__ = [
    "VaultGitStatus",
    "WikiAgentLayoutMigrationResult",
    "WikiVaultMigrationResult",
    "WikiVaultSeedResult",
    "after_wiki_vault_mutation",
    "build_wiki_export_zip",
    "get_wiki_archiver",
    "init_wiki_vault_at_startup",
    "is_agent_layout_migration_complete",
    "is_legacy_migration_complete",
    "is_vault_ready",
    "list_legacy_wiki_vault_paths",
    "migrate_global_wiki_to_agent_layout",
    "migrate_legacy_wiki_vaults",
    "read_vault_git_status",
    "reset_wiki_archiver_cache_for_tests",
    "resolve_agent_wiki_vault_path",
    "resolve_shared_wiki_vault_labels",
    "resolve_shared_wiki_vault_path",
    "resolve_shared_wiki_vault_paths",
    "resolve_wiki_vault_layout",
    "resolve_wiki_vault_path",
    "sanitize_wiki_scope_id",
    "seed_agent_vault_from_default",
    "vault_has_wiki_content",
    "wiki_root",
]
