"""Architecture gate: every core wheel is built on a runner whose CPU is the CPU of its platform key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from harness_packaging.platforms import PUBLISH_PLATFORMS, platform_spec_for_key

_MATRIX_PATH = _REPO_ROOT.parent / ".github" / "core-platform-matrix.json"
_GATE_WORKFLOW = _REPO_ROOT.parent / ".github" / "workflows" / "harness-boundary.yml"

# CPU of every runner label the release may use. A new label is added here on purpose: Nuitka does not
# cross-compile, so the label decides which CPU the compiled modules are built for.
_RUNNER_MACHINE = {
    "macos-15": "arm64",
    "macos-15-intel": "x64",
    "ubuntu-24.04": "x64",
    "ubuntu-24.04-arm": "arm64",
    "windows-2022": "x64",
    "windows-11-arm": "arm64",
}


def _matrix() -> list[dict[str, str]]:
    if not _MATRIX_PATH.is_file():
        pytest.skip("core-platform-matrix.json lives in the repository that holds the publish workflow")
    return json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))


@pytest.mark.architecture
def test_the_matrix_builds_every_published_platform_once() -> None:
    assert sorted(entry["platform"] for entry in _matrix()) == sorted(PUBLISH_PLATFORMS)


@pytest.mark.architecture
def test_every_platform_is_built_on_a_runner_with_its_own_cpu() -> None:
    for entry in _matrix():
        platform_key, runner = entry["platform"], entry["os"]
        assert runner in _RUNNER_MACHINE, f"unknown runner label {runner!r}: record its CPU in _RUNNER_MACHINE"
        machine = platform_spec_for_key(platform_key).machine
        assert _RUNNER_MACHINE[runner] == machine, (
            f"{platform_key} needs a {machine} runner but {runner} is {_RUNNER_MACHINE[runner]}: "
            "Nuitka would compile host code under the wrong platform name"
        )


@pytest.mark.architecture
def test_the_workflow_that_runs_this_gate_runs_when_the_matrix_changes() -> None:
    _matrix()  # skips outside the repository that holds the workflows
    workflow = yaml.safe_load(_GATE_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow[True]  # YAML 1.1 reads the key `on` as the boolean True

    assert ".github/core-platform-matrix.json" in triggers["pull_request"]["paths"], (
        "the matrix sits outside myrm-agent-harness/, so a pull request that only edits it would skip this gate"
    )
