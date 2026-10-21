"""Search provider catalog registry.

[INPUT]
- manifest.json on disk (POS: Search provider catalog manifest)

[OUTPUT]
- SearchProviderCatalogRegistry: Load and query provider manifest entries

[POS]
Server-side search provider catalog SSOT for Settings UI and verify probes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.integrations.search_catalog.models import (
    SearchDeploymentScope,
    SearchProviderManifestEntry,
)

logger = logging.getLogger(__name__)

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
_MAX_CHAIN_SIZE = 5


class SearchProviderCatalogRegistry:
    """In-memory registry of search provider manifest entries."""

    _instance: SearchProviderCatalogRegistry | None = None

    def __init__(self) -> None:
        self._entries: list[SearchProviderManifestEntry] = []
        self._by_slug: dict[str, SearchProviderManifestEntry] = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> SearchProviderCatalogRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self) -> None:
        if not _MANIFEST_PATH.exists():
            logger.warning("Search provider manifest not found: %s", _MANIFEST_PATH)
            return
        raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        entries = [SearchProviderManifestEntry.model_validate(item) for item in raw]
        self._entries = entries
        self._by_slug = {entry.slug: entry for entry in entries}
        logger.info("Loaded %d search provider manifest entries", len(entries))

    def list_all(self) -> list[SearchProviderManifestEntry]:
        self._ensure_loaded()
        return list(self._entries)

    def list_for_deploy_mode(self, *, is_local: bool) -> list[SearchProviderManifestEntry]:
        entries = self.list_all()
        if is_local:
            return entries
        return [entry for entry in entries if entry.deployment_scope != SearchDeploymentScope.LOCAL_TAURI_ONLY]

    def get_by_slug(self, slug: str) -> SearchProviderManifestEntry | None:
        self._ensure_loaded()
        return self._by_slug.get(slug)

    def is_known_slug(self, slug: str) -> bool:
        return self.get_by_slug(slug) is not None

    def is_selectable_slug(self, slug: str) -> bool:
        entry = self.get_by_slug(slug)
        return entry is not None and entry.backend_ready

    @staticmethod
    def max_chain_size() -> int:
        return _MAX_CHAIN_SIZE
