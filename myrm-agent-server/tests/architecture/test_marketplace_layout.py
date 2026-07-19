"""Architecture test: marketplace import/export lives in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_AGENT_SERVICES_ROOT = _SERVER_ROOT / "app" / "services" / "agent"
_MARKETPLACE_PACKAGE = _AGENT_SERVICES_ROOT / "marketplace"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "package_contract.py",
    "export.py",
    "import_.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "marketplace_package_contract.py",
    "marketplace_export.py",
    "marketplace_import.py",
)


@pytest.mark.architecture
def test_marketplace_subpackage_layout() -> None:
    assert _MARKETPLACE_PACKAGE.is_dir(), (
        f"Missing {_MARKETPLACE_PACKAGE}. See app/services/agent/marketplace/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _MARKETPLACE_PACKAGE / filename
        assert path.is_file(), f"Missing required marketplace module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_marketplace_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _AGENT_SERVICES_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat marketplace file must not reappear: {legacy_path}. "
        "Use app/services/agent/marketplace/ instead."
    )
