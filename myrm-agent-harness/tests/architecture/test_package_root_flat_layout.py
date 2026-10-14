"""Architecture test: Python package roots must not flat-spread implementation modules."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PACKAGE_ROOT = _REPO_ROOT / "src" / "myrm_agent_harness"
_CHECK_SCRIPT = _REPO_ROOT / "scripts" / "check_package_root_layout.py"
_TESTS_ROOT = _REPO_ROOT / "tests"

_INSTALL_GUARD_SUBPACKAGE = _PACKAGE_ROOT / "runtime" / "install_guard"

_REQUIRED_SUBPACKAGE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "verify.py",
)


@pytest.mark.architecture
def test_package_root_layout_gate() -> None:
    """Run the CI layout gate end to end: package roots plus the tests/ root."""
    result = subprocess.run(
        [sys.executable, str(_CHECK_SCRIPT), "--root", str(_PACKAGE_ROOT)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


_RUNTIME_ROOT = _PACKAGE_ROOT / "runtime"

_RUNTIME_SUBPACKAGES = (
    "diagnostics",
    "survival",
    "paths",
    "artifacts",
    "fork",
    "deps",
)


@pytest.mark.architecture
def test_runtime_root_has_no_flat_implementation_modules() -> None:
    """runtime/ root must only host __init__.py (domain modules live in subpackages)."""
    forbidden = sorted(
        p.name for p in _RUNTIME_ROOT.iterdir() if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"
    )
    assert not forbidden, (
        f"runtime/ root must not flat-spread modules: {forbidden}. "
        "Move into diagnostics/, survival/, paths/, artifacts/, fork/, or deps/."
    )


@pytest.mark.architecture
def test_runtime_domain_subpackages_exist() -> None:
    for name in _RUNTIME_SUBPACKAGES:
        sub = _RUNTIME_ROOT / name
        assert sub.is_dir(), f"Missing runtime subpackage: {sub}"
        assert (sub / "__init__.py").is_file(), f"Missing {sub}/__init__.py"
        assert (sub / "_ARCH.md").is_file(), f"Missing {sub}/_ARCH.md"


@pytest.mark.architecture
def test_install_guard_subpackage_layout() -> None:
    assert _INSTALL_GUARD_SUBPACKAGE.is_dir(), (
        f"Missing {_INSTALL_GUARD_SUBPACKAGE}. See runtime/install_guard/_ARCH.md."
    )
    for filename in _REQUIRED_SUBPACKAGE_FILES:
        path = _INSTALL_GUARD_SUBPACKAGE / filename
        assert path.is_file(), f"Missing required install_guard module file: {path}"


@pytest.mark.architecture
def test_client_facade_still_at_package_root() -> None:
    client_path = _PACKAGE_ROOT / "client.py"
    assert client_path.is_file(), "SDK facade client.py must remain at package root."
