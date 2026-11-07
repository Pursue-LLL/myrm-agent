"""The architecture gate script judges the push range first and runs both reachability diffs.

A reachability verdict covers one push range and is never judged again: the next push's base already
contains whatever this push left unwired. The whole-tree gates are re-evaluated in full on every run, so a
failure there only postpones them. The script therefore has to judge the push range before the dependency
install and the whole-tree gates, and the harness diff must not hide the server diff. The base of the range
comes from MYRM_REACHABILITY_BASE: a GitHub Actions run without it fails, because the local fallback
origin/main is HEAD itself after a push and would make every diff empty.

The real script and its helper run from a copy of their directory with stub ``python3``, ``uv`` and
``promtool`` that only record their calls, so no gate does any real work.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_CI_DIR = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_BASES_LOG = "bases.log"

# The stub python3 tells the two reachability diffs apart (``--require-server`` selects the harness diff) and
# records the ``--base`` each one received; every other call is recorded and succeeds.
_PYTHON_STUB = """#!/bin/bash
case "$1" in
  */check_module_reachability.py)
    prev=""
    for arg in "$@"; do
      [[ "$prev" == "--base" ]] && echo "$arg" >> "$STUB_BASES"
      prev="$arg"
    done
    if [[ " $* " == *" --require-server "* ]]; then
      echo "reachability:harness" >> "$STUB_LOG"
      exit "${STUB_RC_HARNESS:-0}"
    fi
    echo "reachability:server" >> "$STUB_LOG"
    exit "${STUB_RC_SERVER:-0}" ;;
  *) echo "python3:$(basename "$1")" >> "$STUB_LOG" ;;
esac
"""
_UV_STUB = """#!/bin/bash
echo "uv:$1" >> "$STUB_LOG"
[[ "$1" == "sync" ]] && exit "${STUB_RC_INSTALL:-0}"
exit 0
"""
_PROMTOOL_STUB = """#!/bin/bash
echo "promtool" >> "$STUB_LOG"
"""


def _run_gates(tmp_path: Path, **extra_env: str) -> tuple[int, list[str]]:
    """Run the gate script with ``extra_env`` added to its environment.

    STUB_RC_HARNESS / STUB_RC_SERVER / STUB_RC_INSTALL pick the exit codes of the stubs.
    """
    server = tmp_path / "myrm-agent-server"
    ci_dir = server / "scripts" / "ci"
    ci_dir.mkdir(parents=True)
    for name in ("run_architecture_gates.sh", "lib_harness_deps.sh"):
        shutil.copy(_CI_DIR / name, ci_dir / name)
    harness = tmp_path / "myrm-agent-harness"
    (harness / "scripts").mkdir(parents=True)
    (harness / "pyproject.toml").touch()

    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in {"python3": _PYTHON_STUB, "uv": _UV_STUB, "promtool": _PROMTOOL_STUB}.items():
        (stubs / name).write_text(body, encoding="utf-8")
        (stubs / name).chmod(0o755)

    log = tmp_path / "calls.log"
    log.touch()
    bases = tmp_path / _BASES_LOG
    bases.touch()
    # No CI, GITHUB_ACTIONS or MYRM_* variables unless a test passes them: the gates stay in their local-default state.
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "STUB_LOG": str(log), "STUB_BASES": str(bases), **extra_env}
    done = subprocess.run(
        ["bash", str(ci_dir / "run_architecture_gates.sh")],
        cwd=server,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return done.returncode, log.read_text(encoding="utf-8").split()


def _diff_bases(tmp_path: Path) -> list[str]:
    """The ``--base`` each reachability diff of the last ``_run_gates(tmp_path)`` received, in call order."""
    return (tmp_path / _BASES_LOG).read_text(encoding="utf-8").split()


def test_reachability_diffs_run_before_the_dependency_install_and_the_whole_tree_gates(tmp_path: Path) -> None:
    code, calls = _run_gates(tmp_path)
    assert code == 0
    assert calls[:3] == ["reachability:harness", "reachability:server", "uv:sync"]


@pytest.mark.parametrize("failing", ["STUB_RC_HARNESS", "STUB_RC_SERVER"])
def test_a_failing_diff_does_not_hide_the_other_and_stops_the_run(tmp_path: Path, failing: str) -> None:
    code, calls = _run_gates(tmp_path, **{failing: "1"})
    assert code != 0
    assert calls == ["reachability:harness", "reachability:server"]


def test_a_failing_dependency_install_cannot_skip_the_reachability_verdict(tmp_path: Path) -> None:
    code, calls = _run_gates(tmp_path, STUB_RC_INSTALL="1")
    assert code != 0
    assert calls == ["reachability:harness", "reachability:server", "uv:sync"]


def test_a_github_actions_run_without_a_base_fails_before_any_diff(tmp_path: Path) -> None:
    code, calls = _run_gates(tmp_path, GITHUB_ACTIONS="true")
    assert code != 0
    assert calls == []


def test_the_given_base_reaches_both_diffs(tmp_path: Path) -> None:
    code, _ = _run_gates(tmp_path, GITHUB_ACTIONS="true", MYRM_REACHABILITY_BASE="abc123")
    assert code == 0
    assert _diff_bases(tmp_path) == ["abc123", "abc123"]


def test_a_local_run_falls_back_to_origin_main_even_with_ci_set(tmp_path: Path) -> None:
    # The script's own pyright hint lists CI=true as a way to run that gate locally; only the GitHub runner
    # must supply a base.
    _run_gates(tmp_path, CI="true")
    assert _diff_bases(tmp_path) == ["origin/main", "origin/main"]
