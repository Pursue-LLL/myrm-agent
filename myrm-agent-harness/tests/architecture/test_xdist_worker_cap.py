"""Architecture gate: ``pytest -n N`` never starts more xdist workers than the configured cap.

Each xdist worker is its own Python process, so memory grows with ``-n`` (measured: one ``-n 10`` run held about
12 GiB). The cap is ``--maxprocesses`` in ``pyproject.toml`` ``addopts``; these tests run the repo's real pytest
configuration in a nested ``--collect-only`` session (which spawns no workers) and read the worker list xdist
would start, to prove the cap still bites and can still be raised on purpose.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_PLUGIN_NAME = "xdist_worker_probe"
# ``config.option.tx`` is xdist's worker spec list: one entry per worker it will spawn.
_PLUGIN_SOURCE = (
    "from pathlib import Path\n\n\n"
    "def pytest_sessionstart(session):\n"
    "    Path({report!r}).write_text(str(len(session.config.option.tx)))\n"
)


def _configured_cap() -> int:
    ini_options = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    match = re.search(r"--maxprocesses=(\d+)", ini_options["addopts"])
    assert match, "pyproject.toml addopts must cap xdist workers with --maxprocesses"
    return int(match[1])


def _workers_requested(tmp_path: Path, requested: int, extra_addopts: str = "") -> int:
    """Run ``pytest -n <requested>`` under the repo's own ini and return how many workers xdist would start."""
    report = tmp_path / "workers.txt"
    (tmp_path / f"{_PLUGIN_NAME}.py").write_text(_PLUGIN_SOURCE.format(report=str(report)), encoding="utf-8")
    # An outer xdist worker or addopts would change what the nested run is asked for.
    env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTEST_XDIST", "PYTEST_ADDOPTS"))}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(tmp_path), env.get("PYTHONPATH", "")]))
    if extra_addopts:
        env["PYTEST_ADDOPTS"] = extra_addopts
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(_PYPROJECT),
            "--rootdir",
            str(tmp_path),
            "-p",
            "no:cacheprovider",
            "-p",
            _PLUGIN_NAME,
            "--collect-only",
            "-n",
            str(requested),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=tmp_path,
        timeout=120,
    )
    assert report.exists(), f"probe did not report a worker count:\n{result.stdout}\n{result.stderr}"
    return int(report.read_text(encoding="utf-8"))


@pytest.mark.architecture
def test_explicit_worker_request_is_capped(tmp_path: Path) -> None:
    cap = _configured_cap()
    assert _workers_requested(tmp_path, requested=cap + 6) == cap


@pytest.mark.architecture
def test_cap_can_be_raised_on_purpose(tmp_path: Path) -> None:
    cap = _configured_cap()
    assert _workers_requested(tmp_path, requested=cap + 6, extra_addopts=f"--maxprocesses={cap + 2}") == cap + 2
