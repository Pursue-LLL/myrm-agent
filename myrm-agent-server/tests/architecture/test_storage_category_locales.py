"""Every category of the storage ledger has a label in every locale and a member in the frontend type.

[POS]
tests/architecture/test_storage_category_locales.py

[INPUT]
- myrm_agent_harness.observability.storage_governance::StorageCategory: the categories the ledger can report
- myrm-agent-frontend/locales/*.json: settings.storageGovernance.categories
- myrm-agent-frontend/src/services/system.ts: StorageCategoryKey

[OUTPUT]
- Fails when a category ships without a label in some language. The governance card reads the label
  dynamically (`categories.${category}`), so a missing one silently shows users the raw message key.
- Fails when the frontend `StorageCategoryKey` union and the backend enum disagree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from myrm_agent_harness.observability.storage_governance import StorageCategory

_FRONTEND = Path(__file__).resolve().parents[3] / "myrm-agent-frontend"
_LOCALES = _FRONTEND / "locales"
_SYSTEM_SERVICE = _FRONTEND / "src" / "services" / "system.ts"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not _LOCALES.is_dir(), reason="frontend sources are not part of this checkout")

_CATEGORY_KEY_TYPE_RE = re.compile(r"export type StorageCategoryKey\s*=(?P<body>[^;]+);")
_QUOTED_RE = re.compile(r"'([a-z_]+)'")


def _backend_categories() -> set[str]:
    return {category.value for category in StorageCategory}


@_SKIP_WITHOUT_FRONTEND
@pytest.mark.parametrize("locale_file", sorted(_LOCALES.glob("*.json")), ids=lambda p: p.stem)
def test_every_storage_category_has_a_label(locale_file: Path) -> None:
    labels = json.loads(locale_file.read_text(encoding="utf-8"))["settings"]["storageGovernance"]["categories"]
    unlabeled = sorted(category for category in _backend_categories() if not labels.get(category, "").strip())
    assert unlabeled == []


@_SKIP_WITHOUT_FRONTEND
def test_frontend_category_type_matches_the_backend_enum() -> None:
    match = _CATEGORY_KEY_TYPE_RE.search(_SYSTEM_SERVICE.read_text(encoding="utf-8"))
    assert match, f"StorageCategoryKey type not found in {_SYSTEM_SERVICE}"
    assert set(_QUOTED_RE.findall(match.group("body"))) == _backend_categories()
