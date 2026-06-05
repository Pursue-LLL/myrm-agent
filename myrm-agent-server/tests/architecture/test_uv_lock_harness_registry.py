"""Architecture test: server uv.lock must pin harness from PyPI registry, not editable path."""

from __future__ import annotations

import platform
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_LOCK_PATH = _SERVER_ROOT / "uv.lock"
_HARNESS_VERSION = "0.1.0rc1"


def _pypi_package_exists(package: str, version: str) -> bool:
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "myrm-architecture-test"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except urllib.error.HTTPError:
        return False


def _platform_core_package() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        suffix = "darwin-arm64" if machine in {"arm64", "aarch64"} else "darwin-x64"
    elif system == "linux":
        suffix = "linux-arm64" if machine in {"arm64", "aarch64"} else "linux-x64"
    elif system in {"windows", "mingw", "msys", "cygwin"}:
        suffix = "win32-arm64" if machine in {"arm64", "aarch64"} else "win32-x64"
    else:
        return ""
    return f"myrm-agent-harness-core-{suffix}"


def _harness_sync_lock_ready_on_pypi() -> bool:
    """True when ./myrm harness sync-lock can run (main wheel + platform core on PyPI)."""
    core = _platform_core_package()
    if not core:
        return False
    return _pypi_package_exists("myrm-agent-harness", _HARNESS_VERSION) and _pypi_package_exists(
        core, _HARNESS_VERSION
    )


@pytest.mark.architecture
@pytest.mark.skipif(
    not _harness_sync_lock_ready_on_pypi(),
    reason="harness PyPI release incomplete (core wheel missing); run ./myrm harness sync-lock after full publish",
)
def test_uv_lock_harness_not_editable() -> None:
    """CI installs harness from PyPI; editable lock entries break uv sync --frozen."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    editable_harness = re.search(
        r'name = "myrm-agent-harness"[\s\S]*?source = \{ editable = "(\.\./myrm-agent-harness|\.\./\.\./myrm-agent-harness)" \}',
        text,
    )
    assert editable_harness is None, (
        "myrm-agent-server/uv.lock still pins myrm-agent-harness as editable. "
        "Run: ./myrm harness sync-lock from vortexai root (after harness PyPI publish)."
    )


@pytest.mark.architecture
@pytest.mark.skipif(
    not _harness_sync_lock_ready_on_pypi(),
    reason="harness PyPI release incomplete (core wheel missing); run ./myrm harness sync-lock after full publish",
)
def test_uv_lock_harness_has_registry_source() -> None:
    """After PyPI publish, lock must contain a registry source for myrm-agent-harness."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    registry_harness = re.search(
        r'name = "myrm-agent-harness"[\s\S]*?source = \{ registry = "https://pypi.org/simple" \}',
        text,
    )
    assert registry_harness is not None, (
        "myrm-agent-server/uv.lock has no PyPI registry entry for myrm-agent-harness. "
        "Run: ./myrm harness sync-lock from vortexai root (after harness PyPI publish)."
    )
