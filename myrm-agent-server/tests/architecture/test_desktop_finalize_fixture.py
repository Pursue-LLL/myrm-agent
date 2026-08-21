"""Shell fixture regression for desktop-release finalize platform/signature matching."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE_SCRIPT = _REPO_ROOT / "scripts/ci/desktop-release/finalize-fixture-test.sh"


def test_finalize_fixture_script_passes() -> None:
    assert _FIXTURE_SCRIPT.is_file(), f"Missing fixture script: {_FIXTURE_SCRIPT}"
    completed = subprocess.run(
        ["bash", str(_FIXTURE_SCRIPT)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, f"finalize-fixture-test failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"


def test_pick_platform_asset_missing_and_edge_cases(tmp_path: Path) -> None:
    """Test edge cases: missing signatures, empty directory, invalid platform keys."""
    pick_script = _REPO_ROOT / "scripts/ci/desktop-release/pick-platform-asset.sh"
    assert pick_script.is_file()

    # 1. Empty assets directory -> returns 1 (no asset matched)
    res_empty = subprocess.run(
        ["bash", "-c", f'source "{pick_script}" && pick_platform_asset darwin-aarch64 "{tmp_path}"'],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_empty.returncode == 1
    assert res_empty.stdout.strip() == ""

    # 2. Unknown platform -> returns 1
    res_unknown = subprocess.run(
        ["bash", "-c", f'source "{pick_script}" && pick_platform_asset unknown-platform "{tmp_path}"'],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_unknown.returncode == 1

    # 3. Darwin Intel matching exact pattern
    intel_pkg = tmp_path / "MyrmAgent_x64.app.tar.gz"
    intel_pkg.write_text("intel-content")
    res_intel = subprocess.run(
        ["bash", "-c", f'source "{pick_script}" && pick_platform_asset darwin-x86_64 "{tmp_path}"'],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_intel.returncode == 0
    assert res_intel.stdout.strip() == "MyrmAgent_x64.app.tar.gz"
