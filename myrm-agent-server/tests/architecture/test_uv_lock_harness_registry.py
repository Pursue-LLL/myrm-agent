"""Architecture test: server uv.lock must pin harness from PyPI registry, not editable path."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_LOCK_PATH = _SERVER_ROOT / "uv.lock"


@pytest.mark.architecture
def test_uv_lock_harness_not_editable() -> None:
    """CI installs harness from PyPI; editable lock entries break uv sync --frozen."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    editable_harness = re.search(
        r'name = "myrm-agent-harness"[\s\S]*?source = \{ editable = "(\.\./myrm-agent-harness|\.\./\.\./myrm-agent-harness)" \}',
        text,
    )
    assert editable_harness is None, (
        "myrm-agent-server/uv.lock still pins myrm-agent-harness as editable. "
        "Run scripts/ci/sync_server_lock_from_pypi.sh after PyPI publish."
    )


@pytest.mark.architecture
def test_uv_lock_harness_has_registry_source() -> None:
    """After PyPI publish, lock must contain a registry source for myrm-agent-harness."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    registry_harness = re.search(
        r'name = "myrm-agent-harness"[\s\S]*?source = \{ registry = "https://pypi.org/simple" \}',
        text,
    )
    assert registry_harness is not None, (
        "myrm-agent-server/uv.lock has no PyPI registry entry for myrm-agent-harness. "
        "Run scripts/ci/sync_server_lock_from_pypi.sh after PyPI publish."
    )
