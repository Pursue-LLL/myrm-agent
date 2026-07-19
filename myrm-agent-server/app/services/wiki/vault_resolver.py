"""Wiki vault path resolution and legacy directory migration.

[INPUT]
- app.config.settings::DatabaseSettings (POS: workspace layout and database connection parameters)

[OUTPUT]
- resolve_wiki_vault_path(): agent-scoped wiki base directory
- resolve_wiki_vault_layout(): primary vault + shared read-only vaults
- list_legacy_wiki_vault_paths(): directories that may hold pre-unification data
- migrate_legacy_wiki_vaults(): one-time copy-merge into canonical vault
- migrate_global_wiki_to_agent_layout(): one-time move flat wiki tree to agents/default/

[POS]
Single source of truth for wiki filesystem layout.
Root: ``{harness_dir}/wiki``; agent vaults: ``agents/{agent_id}/``; shared: ``shared/{context_id}/``.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_LEGACY_MIGRATION_MARKER = ".wiki_legacy_merged"
_AGENT_LAYOUT_MARKER = ".wiki_agent_layout_migrated"
_SCOPE_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_RESERVED_ROOT_NAMES = frozenset({"agents", "shared", _LEGACY_MIGRATION_MARKER, _AGENT_LAYOUT_MARKER})


@dataclass(frozen=True, slots=True)
class WikiVaultMigrationResult:
    """Outcome of a legacy vault migration run."""

    skipped: bool
    canonical_path: Path
    files_copied: int
    legacy_sources: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class WikiAgentLayoutMigrationResult:
    """Outcome of moving a flat wiki tree into ``agents/default/``."""

    skipped: bool
    target_path: Path
    entries_moved: int


def wiki_root() -> Path:
    """Return the wiki filesystem root (contains agents/ and shared/ subtrees)."""
    from app.config.settings import settings

    return Path(settings.database.harness_dir).expanduser().resolve() / "wiki"


def sanitize_wiki_scope_id(scope_id: str | None, *, fallback: str = "default") -> str:
    """Normalize an agent or shared-context identifier for filesystem use."""
    raw = (scope_id or "").strip()
    if not raw:
        return fallback
    sanitized = _SCOPE_ID_PATTERN.sub("_", raw).strip("_")
    return sanitized or fallback


def resolve_agent_wiki_vault_path(agent_id: str | None = None) -> Path:
    """Return the writable wiki vault for a single agent."""
    safe_id = sanitize_wiki_scope_id(agent_id)
    return wiki_root() / "agents" / safe_id


def resolve_shared_wiki_vault_path(context_id: str) -> Path:
    """Return a shared read-only wiki vault for a shared memory context."""
    safe_id = sanitize_wiki_scope_id(context_id)
    return wiki_root() / "shared" / safe_id


def resolve_shared_wiki_vault_paths(context_ids: list[str] | None) -> tuple[Path, ...]:
    """Return shared wiki vault paths deduplicated in request order."""
    if not context_ids:
        return ()
    seen: set[str] = set()
    paths: list[Path] = []
    for context_id in context_ids:
        safe_id = sanitize_wiki_scope_id(context_id)
        if safe_id in seen:
            continue
        seen.add(safe_id)
        paths.append(wiki_root() / "shared" / safe_id)
    return tuple(paths)


def resolve_wiki_vault_layout(
    agent_id: str | None = None,
    shared_context_ids: list[str] | None = None,
) -> tuple[Path, tuple[Path, ...]]:
    """Return (primary_agent_vault, shared_readonly_vaults)."""
    return resolve_agent_wiki_vault_path(agent_id), resolve_shared_wiki_vault_paths(shared_context_ids)


def resolve_wiki_vault_path(agent_id: str | None = None) -> Path:
    """Return the primary agent wiki vault base directory."""
    return resolve_agent_wiki_vault_path(agent_id)


def list_legacy_wiki_vault_paths() -> tuple[Path, ...]:
    """Return legacy wiki directories that may contain user data."""
    from app.config.settings import settings

    state_dir = Path(settings.database.state_dir).expanduser().resolve()
    sandbox_wiki = Path("~/.myrm/users").expanduser().resolve() / "sandbox" / "wiki"
    return (state_dir / "wiki", sandbox_wiki)


def migrate_legacy_wiki_vaults() -> WikiVaultMigrationResult:
    """Copy-merge legacy wiki trees into the default agent vault (idempotent, non-destructive)."""
    wiki_root().mkdir(parents=True, exist_ok=True)
    default_vault = resolve_agent_wiki_vault_path("default")
    default_vault.mkdir(parents=True, exist_ok=True)

    marker = wiki_root() / _LEGACY_MIGRATION_MARKER
    legacy_sources = list_legacy_wiki_vault_paths()

    layout_result = migrate_global_wiki_to_agent_layout()

    if marker.exists():
        return WikiVaultMigrationResult(
            skipped=True,
            canonical_path=layout_result.target_path,
            files_copied=0,
            legacy_sources=legacy_sources,
        )

    files_copied = 0
    for legacy_root in legacy_sources:
        if not legacy_root.exists():
            continue
        try:
            legacy_resolved = legacy_root.resolve()
        except OSError:
            continue
        if legacy_resolved == default_vault.resolve() or legacy_resolved == wiki_root().resolve():
            continue
        files_copied += _merge_tree_copy(legacy_resolved, default_vault)

    marker.write_text("1\n", encoding="utf-8")
    if files_copied:
        logger.warning(
            "Wiki legacy vault migration copied %d files into %s from %s",
            files_copied,
            default_vault,
            [str(p) for p in legacy_sources],
        )
    elif layout_result.entries_moved:
        logger.info(
            "Wiki agent layout migration moved %d entries into %s",
            layout_result.entries_moved,
            layout_result.target_path,
        )
    else:
        logger.info("Wiki legacy vault migration: no files to copy (default_vault=%s)", default_vault)

    return WikiVaultMigrationResult(
        skipped=False,
        canonical_path=default_vault,
        files_copied=files_copied,
        legacy_sources=legacy_sources,
    )


def migrate_global_wiki_to_agent_layout() -> WikiAgentLayoutMigrationResult:
    """Move a pre-layout flat wiki tree at the root into ``agents/default/``."""
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _AGENT_LAYOUT_MARKER
    default_vault = resolve_agent_wiki_vault_path("default")

    if marker.exists():
        return WikiAgentLayoutMigrationResult(skipped=True, target_path=default_vault, entries_moved=0)

    legacy_entries = _list_flat_layout_entries(root)
    if not legacy_entries:
        marker.write_text("1\n", encoding="utf-8")
        default_vault.mkdir(parents=True, exist_ok=True)
        return WikiAgentLayoutMigrationResult(skipped=False, target_path=default_vault, entries_moved=0)

    default_vault.mkdir(parents=True, exist_ok=True)
    moved = 0
    for entry in legacy_entries:
        destination = default_vault / entry.name
        if destination.exists():
            if entry.is_dir():
                moved += _merge_tree_copy(entry, destination)
            continue
        shutil.move(str(entry), str(destination))
        moved += 1

    marker.write_text("1\n", encoding="utf-8")
    if moved:
        logger.warning(
            "Wiki agent layout migration moved %d entries from %s to %s",
            moved,
            root,
            default_vault,
        )
    return WikiAgentLayoutMigrationResult(skipped=False, target_path=default_vault, entries_moved=moved)


def is_legacy_migration_complete() -> bool:
    """Return True when legacy wiki directories have been merged into the wiki root."""
    marker = wiki_root() / _LEGACY_MIGRATION_MARKER
    return marker.is_file()


def is_agent_layout_migration_complete() -> bool:
    """Return True when flat wiki content has been moved under agents/default/."""
    marker = wiki_root() / _AGENT_LAYOUT_MARKER
    return marker.is_file()


def is_vault_ready(agent_id: str | None = None) -> bool:
    """Return True when the agent wiki vault directory layout exists."""
    vault = resolve_agent_wiki_vault_path(agent_id)
    return vault.is_dir() and (vault / "raw").is_dir()


def _list_flat_layout_entries(root: Path) -> list[Path]:
    """Return root-level wiki entries that belong to the legacy flat layout."""
    entries: list[Path] = []
    for entry in root.iterdir():
        if entry.name in _RESERVED_ROOT_NAMES:
            continue
        if entry.name.startswith("."):
            continue
        entries.append(entry)
    return entries


def _merge_tree_copy(source_root: Path, target_root: Path) -> int:
    """Recursively copy files from source into target, skipping existing targets."""
    if not source_root.is_dir():
        return 0

    copied = 0
    for src in source_root.rglob("*"):
        if not src.is_file():
            continue
        if src.name in {_LEGACY_MIGRATION_MARKER, _AGENT_LAYOUT_MARKER}:
            continue
        rel = src.relative_to(source_root)
        dest = target_root / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied
