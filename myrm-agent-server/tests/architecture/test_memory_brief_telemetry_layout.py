"""Architecture test: memory brief CP telemetry lives in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_AGENT_SERVICES_ROOT = _SERVER_ROOT / "app" / "services" / "agent"
_TELEMETRY_PACKAGE = _AGENT_SERVICES_ROOT / "memory_brief_telemetry"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "contract.py",
    "dispatcher.py",
    "dropped_store.py",
    "flush.py",
    "metrics.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "memory_brief_status_contract.py",
    "memory_brief_status_dropped_store.py",
    "memory_brief_status_telemetry.py",
    "memory_brief_status_telemetry_flush.py",
    "memory_brief_status_telemetry_metrics.py",
    "memory_brief_status_dropped_state.py",
)


@pytest.mark.architecture
def test_memory_brief_telemetry_subpackage_layout() -> None:
    assert _TELEMETRY_PACKAGE.is_dir(), (
        f"Missing {_TELEMETRY_PACKAGE}. See app/services/agent/memory_brief_telemetry/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _TELEMETRY_PACKAGE / filename
        assert path.is_file(), f"Missing required telemetry module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_memory_brief_telemetry_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _AGENT_SERVICES_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat telemetry file must not reappear: {legacy_path}. "
        "Use app/services/agent/memory_brief_telemetry/ instead."
    )
