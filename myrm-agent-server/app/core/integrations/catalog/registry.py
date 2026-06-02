"""Integration Catalog Registry.

Loads preconfigured service entries from bundled JSON data files and provides
query capabilities (list, search, get by id).
"""

import json
import logging
from pathlib import Path

from app.core.integrations.catalog.models import CatalogEntry

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


class CatalogRegistry:
    """In-memory registry of preconfigured integration services.

    Lazily loads entries from JSON files under the data/ directory on first access.
    Thread-safe for reads after initialization.
    """

    _instance: "CatalogRegistry | None" = None
    _entries: list[CatalogEntry]
    _by_id: dict[str, CatalogEntry]

    def __init__(self) -> None:
        self._entries = []
        self._by_id = {}
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "CatalogRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load_all()
        self._loaded = True

    def _load_all(self) -> None:
        if not _DATA_DIR.exists():
            logger.warning("Integration catalog data directory not found: %s", _DATA_DIR)
            return

        entries: list[CatalogEntry] = []
        for json_file in sorted(_DATA_DIR.glob("*.json")):
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for item in raw:
                        entries.append(CatalogEntry.model_validate(item))
                elif isinstance(raw, dict):
                    entries.append(CatalogEntry.model_validate(raw))
            except Exception as e:
                logger.error("Failed to load catalog file %s: %s", json_file.name, e)

        self._entries = entries
        self._by_id = {e.id: e for e in entries}
        logger.info("Loaded %d integration catalog entries", len(entries))

    def list_all(self) -> list[CatalogEntry]:
        """Return all catalog entries."""
        self._ensure_loaded()
        return list(self._entries)

    def get_by_id(self, entry_id: str) -> CatalogEntry | None:
        """Get a single entry by ID."""
        self._ensure_loaded()
        return self._by_id.get(entry_id)

    def search(self, query: str) -> list[CatalogEntry]:
        """Search entries by name, description, or tags."""
        self._ensure_loaded()
        q = query.lower()
        results: list[CatalogEntry] = []
        for entry in self._entries:
            if (
                q in entry.name.lower()
                or q in entry.description.lower()
                or q in entry.name_zh.lower()
                or q in entry.description_zh.lower()
                or any(q in tag.lower() for tag in entry.tags)
            ):
                results.append(entry)
        return results

    def list_by_category(self, category: str) -> list[CatalogEntry]:
        """Filter entries by category."""
        self._ensure_loaded()
        return [e for e in self._entries if e.category == category]

    def get_categories(self) -> list[str]:
        """Return all unique categories."""
        self._ensure_loaded()
        seen: set[str] = set()
        result: list[str] = []
        for e in self._entries:
            if e.category not in seen:
                seen.add(e.category)
                result.append(e.category)
        return result
