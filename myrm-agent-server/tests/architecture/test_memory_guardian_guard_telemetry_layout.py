"""Architecture test: memory guardian guard CP telemetry lives in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_AGENT_SERVICES_ROOT = _SERVER_ROOT / "app" / "services" / "agent"
_TELEMETRY_PACKAGE = _AGENT_SERVICES_ROOT / "memory_guardian_guard_telemetry"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "dispatcher.py",
    "pending_store.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "memory_guardian_guard_telemetry.py",
    "memory_guardian_guard_pending_store.py",
)


@pytest.mark.architecture
def test_memory_guardian_guard_telemetry_subpackage_layout() -> None:
    assert _TELEMETRY_PACKAGE.is_dir(), (
        f"Missing {_TELEMETRY_PACKAGE}. See app/services/agent/memory_guardian_guard_telemetry/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _TELEMETRY_PACKAGE / filename
        assert path.is_file(), f"Missing required guardian guard telemetry module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_memory_guardian_guard_telemetry_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _AGENT_SERVICES_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat guardian guard telemetry file must not reappear: {legacy_path}. "
        "Use app/services/agent/memory_guardian_guard_telemetry/ instead."
    )
