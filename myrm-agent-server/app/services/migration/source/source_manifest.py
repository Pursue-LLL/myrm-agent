"""Migration source manifest (single source of truth).

[INPUT]
Migration Wizard source policy from ``services/migration/_ARCH.md``.

[OUTPUT]
- source manifest entries for frontend downlink
- local-scan source id set (five-source closure)
- discovery-id to memory-import-source map

[POS]
Centralizes Wizard migration source metadata to avoid frontend/backend drift.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal, TypedDict

MigrationSourceDiscoverMode = Literal["local_scan", "zip_upload"]
MigrationImportSource = Literal["hermes", "openclaw", "claude", "codex", "chatgpt", "gemini", "gbrain", "pi", "plur"]
MIGRATION_SOURCE_MANIFEST_AUTHORITATIVE: Final[bool] = True


class MigrationSourceManifestPayloadItem(TypedDict):
    """JSON-safe manifest item shared by API and command-center responses."""

    id: str
    display_name: str
    import_source: MigrationImportSource
    discover_modes: list[MigrationSourceDiscoverMode]
    deep_link_enabled: bool


@dataclass(frozen=True, slots=True)
class MigrationSourceManifestEntry:
    """Declarative metadata for one migration source id."""

    id: str
    display_name: str
    import_source: MigrationImportSource
    discover_modes: tuple[MigrationSourceDiscoverMode, ...]
    deep_link_enabled: bool = True


_MIGRATION_SOURCE_MANIFEST: tuple[MigrationSourceManifestEntry, ...] = (
    MigrationSourceManifestEntry(
        id="hermes",
        display_name="Hermes",
        import_source="hermes",
        discover_modes=("local_scan",),
    ),
    MigrationSourceManifestEntry(
        id="openclaw",
        display_name="OpenClaw",
        import_source="openclaw",
        discover_modes=("local_scan",),
    ),
    MigrationSourceManifestEntry(
        id="claude",
        display_name="Claude Code",
        import_source="claude",
        discover_modes=("local_scan",),
    ),
    MigrationSourceManifestEntry(
        id="codex",
        display_name="Codex",
        import_source="codex",
        discover_modes=("local_scan",),
    ),
    MigrationSourceManifestEntry(
        id="chatgpt",
        display_name="ChatGPT",
        import_source="chatgpt",
        discover_modes=("zip_upload",),
    ),
    MigrationSourceManifestEntry(
        id="gemini",
        display_name="Google Gemini",
        import_source="gemini",
        discover_modes=("zip_upload",),
    ),
    MigrationSourceManifestEntry(
        id="gbrain",
        display_name="gbrain",
        import_source="gbrain",
        discover_modes=("zip_upload",),
    ),
    MigrationSourceManifestEntry(
        id="pi",
        display_name="Pi",
        import_source="pi",
        discover_modes=("local_scan",),
    ),
    MigrationSourceManifestEntry(
        id="plur",
        display_name="PLUR",
        import_source="plur",
        discover_modes=("zip_upload",),
    ),
)


def migration_source_manifest_entries() -> tuple[MigrationSourceManifestEntry, ...]:
    """Return immutable migration source manifest entries."""

    return _MIGRATION_SOURCE_MANIFEST


def migration_source_manifest_ids() -> frozenset[str]:
    """Return the canonical migration source id set declared by SSOT."""

    return frozenset(entry.id for entry in _MIGRATION_SOURCE_MANIFEST)


def migration_source_manifest_authoritative() -> bool:
    """Return whether server payload should replace frontend local defaults."""

    return MIGRATION_SOURCE_MANIFEST_AUTHORITATIVE


def migration_source_manifest_authoritative_for_ids(source_ids: Iterable[str]) -> bool:
    """Return authoritative only when payload ids fully cover the SSOT set."""

    if not MIGRATION_SOURCE_MANIFEST_AUTHORITATIVE:
        return False
    normalized_ids = frozenset(source_id.strip().lower() for source_id in source_ids if source_id.strip())
    return migration_source_manifest_ids().issubset(normalized_ids)


def migration_source_manifest_payload() -> list[MigrationSourceManifestPayloadItem]:
    """Return JSON-safe manifest payload for API responses."""

    return [
        {
            "id": entry.id,
            "display_name": entry.display_name,
            "import_source": entry.import_source,
            "discover_modes": list(entry.discover_modes),
            "deep_link_enabled": entry.deep_link_enabled,
        }
        for entry in _MIGRATION_SOURCE_MANIFEST
    ]


def migration_source_import_map() -> dict[str, MigrationImportSource]:
    """Map migration discovery source id -> memory import source id."""

    return {entry.id: entry.import_source for entry in _MIGRATION_SOURCE_MANIFEST}


def migration_source_display_name(source_id: str) -> str:
    """Return display name for a source id; fallback to raw id."""

    normalized = source_id.strip().lower()
    for entry in _MIGRATION_SOURCE_MANIFEST:
        if entry.id == normalized:
            return entry.display_name
    return normalized or source_id


def migration_source_local_scan_ids() -> frozenset[str]:
    """Return source ids discovered by local filesystem scan."""

    return frozenset(entry.id for entry in _MIGRATION_SOURCE_MANIFEST if "local_scan" in entry.discover_modes)


def migration_source_deep_link_ids() -> frozenset[str]:
    """Return source ids that should be preserved in `?source=` deep links."""

    return frozenset(entry.id for entry in _MIGRATION_SOURCE_MANIFEST if entry.deep_link_enabled)
