"""Static regression for desktop launch runtime smoke scripts (macOS/Linux & Windows)."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SMOKE_SCRIPT_SH = _REPO_ROOT / "scripts/ci/desktop-release/smoke-launch-runtime.sh"
_SMOKE_SCRIPT_PS1 = _REPO_ROOT / "scripts/ci/desktop-release/smoke-launch-runtime.ps1"


def test_smoke_launch_runtime_script_sh_syntax() -> None:
    assert _SMOKE_SCRIPT_SH.is_file(), f"Missing smoke script: {_SMOKE_SCRIPT_SH}"
    completed = subprocess.run(
        ["bash", "-n", str(_SMOKE_SCRIPT_SH)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"smoke-launch-runtime.sh syntax error:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )

    text = _SMOKE_SCRIPT_SH.read_text(encoding="utf-8")
    assert "--bundle-app" in text
    assert "/health" in text
    assert "MIN_BINARY_BYTES" in text
    assert "AGENT_RUNNER_BIN" in text


def test_smoke_launch_runtime_script_ps1_content() -> None:
    assert _SMOKE_SCRIPT_PS1.is_file(), f"Missing smoke script: {_SMOKE_SCRIPT_PS1}"
    text = _SMOKE_SCRIPT_PS1.read_text(encoding="utf-8")
    assert "-Dev" in text
    assert "-BundleDir" in text
    assert "/health" in text
    assert "MinBinaryBytes" in text
    assert "Assert-NonEmptyFile" in text
    assert "Kill-ProcessTree" in text
    assert "taskkill.exe" in text
