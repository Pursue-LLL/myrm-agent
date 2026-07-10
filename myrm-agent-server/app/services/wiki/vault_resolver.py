"""Wiki vault path resolution and legacy directory migration.

[INPUT]
- app.config.settings::DatabaseSettings (POS: workspace layout and database connection parameters)

[OUTPUT]
- resolve_wiki_vault_path(): canonical wiki base directory
- list_legacy_wiki_vault_paths(): directories that may hold pre-unification data
- migrate_legacy_wiki_vaults(): one-time copy-merge into canonical vault

[POS]
Single source of truth for wiki filesystem layout. Canonical location: ``{harness_dir}/wiki``.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_MARKER = ".wiki_legacy_merged"


@dataclass(frozen=True, slots=True)
class WikiVaultMigrationResult:
    """Outcome of a legacy vault migration run."""

    skipped: bool
    canonical_path: Path
    files_copied: int
    legacy_sources: tuple[Path, ...]


def resolve_wiki_vault_path() -> Path:
    """Return the canonical wiki vault base directory."""
    from app.config.settings import settings

    return Path(settings.database.harness_dir).expanduser().resolve() / "wiki"


def list_legacy_wiki_vault_paths() -> tuple[Path, ...]:
    """Return legacy wiki directories that may contain user data."""
    from app.config.settings import settings

    state_dir = Path(settings.database.state_dir).expanduser().resolve()
    sandbox_wiki = Path("~/.myrm/users").expanduser().resolve() / "sandbox" / "wiki"
    return (state_dir / "wiki", sandbox_wiki)


def migrate_legacy_wiki_vaults() -> WikiVaultMigrationResult:
    """Copy-merge legacy wiki trees into the canonical vault (idempotent, non-destructive)."""
    canonical = resolve_wiki_vault_path()
    canonical.mkdir(parents=True, exist_ok=True)

    marker = canonical / _MIGRATION_MARKER
    legacy_sources = list_legacy_wiki_vault_paths()

    if marker.exists():
        return WikiVaultMigrationResult(
            skipped=True,
            canonical_path=canonical,
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
        if legacy_resolved == canonical.resolve():
            continue
        files_copied += _merge_tree_copy(legacy_resolved, canonical)

    marker.write_text("1\n", encoding="utf-8")
    if files_copied:
        logger.warning(
            "Wiki legacy vault migration copied %d files into %s from %s",
            files_copied,
            canonical,
            [str(p) for p in legacy_sources],
        )
    else:
        logger.info("Wiki legacy vault migration: no files to copy (canonical=%s)", canonical)

    return WikiVaultMigrationResult(
        skipped=False,
        canonical_path=canonical,
        files_copied=files_copied,
        legacy_sources=legacy_sources,
    )


def is_legacy_migration_complete() -> bool:
    """Return True when legacy wiki directories have been merged into the canonical vault."""
    marker = resolve_wiki_vault_path() / _MIGRATION_MARKER
    return marker.is_file()


def is_vault_ready() -> bool:
    """Return True when the canonical wiki vault directory layout exists."""
    vault = resolve_wiki_vault_path()
    return vault.is_dir() and (vault / "raw").is_dir()


def _merge_tree_copy(source_root: Path, target_root: Path) -> int:
    """Recursively copy files from source into target, skipping existing targets."""
    if not source_root.is_dir():
        return 0

    copied = 0
    for src in source_root.rglob("*"):
        if not src.is_file():
            continue
        if src.name == _MIGRATION_MARKER:
            continue
        rel = src.relative_to(source_root)
        dest = target_root / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied
