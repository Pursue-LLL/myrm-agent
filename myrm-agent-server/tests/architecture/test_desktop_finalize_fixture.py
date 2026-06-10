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
    assert completed.returncode == 0, (
        f"finalize-fixture-test failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )
