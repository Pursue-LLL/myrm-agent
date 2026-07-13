"""Static regression for desktop launch runtime smoke script."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SMOKE_SCRIPT = _REPO_ROOT / "scripts/ci/desktop-release/smoke-launch-runtime.sh"


def test_smoke_launch_runtime_script_syntax() -> None:
    assert _SMOKE_SCRIPT.is_file(), f"Missing smoke script: {_SMOKE_SCRIPT}"
    completed = subprocess.run(
        ["bash", "-n", str(_SMOKE_SCRIPT)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"smoke-launch-runtime.sh syntax error:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )

    text = _SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "--bundle-app" in text
    assert "/health" in text
    assert "MIN_BINARY_BYTES" in text
