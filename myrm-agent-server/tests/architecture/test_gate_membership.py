"""Behaviour of the gate-membership hook and the workflows that run the files it leaves out.

[INPUT]
- tests/architecture/conftest.py: the `pytest_itemcollected` hook and the `RUN_BY_OTHER_WORKFLOWS` names it leaves out
- .github/workflows/*.yml: the `run` command of every step, read through tests/support/desktop_release.py

[OUTPUT]
- that the hook marks every file except the ones named in `RUN_BY_OTHER_WORKFLOWS`, and that a workflow command runs each of those

[POS]
The hook is the one place that can drop a test from the gate, and a file left out of the gate is safe only while a workflow
still runs it, so this file pins both instead of trusting them. Its tests carry their own mark, so a broken hook cannot
deselect them as well.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.support.desktop_release import WORKFLOWS, YamlMapping, workflow_jobs

_ARCHITECTURE = Path(__file__).resolve().parent


class _CollectedItem:
    """The two members the hook uses; recording the added markers keeps the check free of a nested pytest run."""

    def __init__(self, file_name: str) -> None:
        self.path = _ARCHITECTURE / file_name
        self.marker_names: list[str] = []

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        self.marker_names.append(marker.name)


def _load_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location("architecture_conftest_under_test", _ARCHITECTURE / "conftest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow_commands() -> list[str]:
    commands: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for job in workflow_jobs(workflow.name).values():
            steps = cast("list[YamlMapping]", job.get("steps", []))
            commands.extend(run for step in steps if isinstance(run := step.get("run"), str))
    return commands


# The two `_extra` names are not real files; they pin that a longer name is not taken for a file another workflow runs.
@pytest.mark.architecture
@pytest.mark.parametrize(
    ("file_name", "joins_gate"),
    [
        ("test_gate_workflow_triggers.py", True),
        ("test_no_credential_literals_extra.py", True),
        ("test_no_private_references_extra.py", True),
        ("test_desktop_release_gates.py", False),
        ("test_no_credential_literals.py", False),
        ("test_no_private_references.py", False),
    ],
)
def test_the_hook_marks_every_file_except_those_another_workflow_runs(file_name: str, joins_gate: bool) -> None:
    item = _CollectedItem(file_name)
    hook: Callable[[pytest.Item], None] = _load_conftest().pytest_itemcollected
    hook(cast("pytest.Item", item))

    assert item.marker_names == (["architecture"] if joins_gate else [])


@pytest.mark.architecture
@pytest.mark.parametrize("name", _load_conftest().RUN_BY_OTHER_WORKFLOWS)
def test_a_workflow_runs_every_file_the_hook_leaves_out(name: str) -> None:
    pattern = f"{name}py" if name.endswith(".") else f"{name}*.py"

    assert any(pattern in command for command in _workflow_commands()), f"no workflow command runs {pattern}"
