"""Every integration catalog category has a display name in every locale.

[POS]
tests/architecture/test_catalog_category_locales.py

[INPUT]
- app.core.integrations.catalog.registry::CatalogRegistry.get_categories: the categories the catalog API returns
- myrm-agent-frontend/locales/*.json: settings.integrationCatalog.categories

[OUTPUT]
- Fails when a category ships without a name in some language. The catalog page reads these keys
  dynamically (`categories.${id}`), so a missing one silently shows users the internal category id.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.integrations.catalog.registry import CatalogRegistry

_LOCALES = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not _LOCALES.is_dir(), reason="frontend sources are not part of this checkout")


@_SKIP_WITHOUT_FRONTEND
@pytest.mark.parametrize("locale_file", sorted(_LOCALES.glob("*.json")), ids=lambda p: p.stem)
def test_every_catalog_category_has_a_display_name(locale_file: Path) -> None:
    categories = CatalogRegistry().get_categories()
    assert categories, "the catalog registry returned no categories, so this check would pass without checking anything"
    names = json.loads(locale_file.read_text(encoding="utf-8"))["settings"]["integrationCatalog"]["categories"]
    unnamed = [category for category in categories if not names.get(category, "").strip()]
    assert unnamed == []
