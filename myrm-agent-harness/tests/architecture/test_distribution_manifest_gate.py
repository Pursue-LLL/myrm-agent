"""Architecture gate: algorithm-zone modules must be manifest-covered or explicitly public."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from harness_packaging import integrity
from harness_packaging.integrity import DISTRIBUTION_PUBLIC_MARKER, manifest_watch_violations, stale_public_subdirs

_GATE_HINT = (
    f"Add the directory to harness_packaging/core_manifest.yaml or mark the module with "
    f"{DISTRIBUTION_PUBLIC_MARKER} in its docstring/header."
)


@pytest.mark.architecture
def test_manifest_watch_violations_empty_on_current_tree() -> None:
    assert manifest_watch_violations() == ()


@pytest.mark.architecture
def test_algorithm_zone_modules_are_manifest_covered_or_public() -> None:
    """Prevent accidental plaintext IP in release wheels under algorithm watch zones."""
    violations = manifest_watch_violations()
    if violations:
        joined = "\n  - ".join(violations)
        pytest.fail(f"Algorithm-zone modules missing manifest coverage or public marker:\n  - {joined}\n{_GATE_HINT}")


@pytest.mark.architecture
def test_watch_zones_and_public_subdirs_name_existing_directories() -> None:
    """A name or zone without a directory would silently exempt or skip whatever is created there later."""
    stale = stale_public_subdirs()
    if stale:
        joined = "\n  - ".join(stale)
        pytest.fail(f"_PARENT_WATCH_ZONES entries with no directory (fix or remove them):\n  - {joined}")


@pytest.mark.architecture
def test_stale_public_subdirs_reports_missing_names_and_missing_zones(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stale-entry check must be able to fail: a vanished allowlist name or zone is reported, not skipped."""
    monkeypatch.setattr(
        integrity,
        "_PARENT_WATCH_ZONES",
        (
            ("agent/skills/", frozenset({"no_such_subdir"})),
            ("no_such_zone/", frozenset({"anything"})),
        ),
    )
    assert stale_public_subdirs() == ("agent/skills/no_such_subdir", "no_such_zone/")
