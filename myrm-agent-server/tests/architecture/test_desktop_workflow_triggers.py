"""The desktop contracts job runs whenever a file the contracts read changes.

[INPUT]
- .github/workflows/desktop-contracts.yml: the `paths` filters of its push and pull_request triggers
- tests/architecture/test_desktop_*.py and the tests/support modules they import: the code the job itself runs
- tests/support/desktop_release.py: the locations of the desktop project, its CI scripts, workflows and actions

[OUTPUT]
That a push and a pull request are judged by the same files, that a new file anywhere in the desktop project, in
its CI scripts, in a desktop workflow or in a local action triggers the job, and so does every test and support
module the job runs.

[POS]
A hand-kept list of the files the contracts read stops covering a file the day a test starts reading it, and the
break then surfaces on an unrelated run. Whole directories are listed instead, and this test keeps it that way.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from tests.support.desktop_release import ACTIONS, CI_SCRIPTS, DESKTOP, REPO_ROOT, WORKFLOWS

_EVENTS = ("push", "pull_request")
_SERVER = REPO_ROOT / "myrm-agent-server"
_SUPPORT_PREFIX = "tests.support."


def _path_filters() -> dict[str, list[str]]:
    workflow = yaml.safe_load((WORKFLOWS / "desktop-contracts.yml").read_text(encoding="utf-8"))
    triggers = workflow[True]  # YAML 1.1 reads the key `on` as the boolean True
    return {event: triggers[event]["paths"] for event in _EVENTS}


def _matches(pattern: str, path: str) -> bool:
    """GitHub's path filter: `*` stays inside one path segment, `**` crosses segments."""
    special = sorted(set("?[]!+") & set(pattern))
    assert not special, f"{pattern!r} uses {special}, which a path filter reads differently from a shell glob"
    regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.fullmatch(regex, path) is not None


def _triggers(event: str, path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT).as_posix()
    return any(_matches(pattern, relative) for pattern in _path_filters()[event])


def _support_modules_imported_by(source: Path) -> set[Path]:
    imported: set[Path] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(_SUPPORT_PREFIX):
            imported.add(_SERVER / Path(*node.module.split(".")).with_suffix(".py"))
    return imported


def _files_the_job_runs() -> set[Path]:
    tests = set((_SERVER / "tests/architecture").glob("test_desktop_*.py"))
    found, pending = set(tests), list(tests)
    while pending:
        for module in _support_modules_imported_by(pending.pop()) - found:
            found.add(module)
            pending.append(module)
    return found


def test_a_push_and_a_pull_request_are_judged_by_the_same_files() -> None:
    filters = _path_filters()

    assert filters["push"] == filters["pull_request"]


@pytest.mark.parametrize("event", _EVENTS)
def test_a_new_file_in_any_part_of_the_release_pipeline_triggers_the_contracts(event: str) -> None:
    new_files = {
        "the desktop project": DESKTOP / "src-tauri/src/a/new/module.rs",
        "the release CI scripts": CI_SCRIPTS / "a-new-script.sh",
        "a desktop workflow": WORKFLOWS / "desktop-a-new-one.yml",
        "a local action": ACTIONS / "a-new-action/action.yml",
    }

    unmatched = [label for label, path in new_files.items() if not _triggers(event, path)]

    assert not unmatched, f"a {event} that only adds a file to {unmatched} would not run the desktop contracts"


@pytest.mark.parametrize("event", _EVENTS)
def test_every_test_and_support_module_the_job_runs_triggers_it(event: str) -> None:
    files = _files_the_job_runs()

    unmatched = sorted(path.relative_to(REPO_ROOT).as_posix() for path in files if not _triggers(event, path))

    assert files and not unmatched, f"a {event} that only edits one of these would not run the desktop contracts: {unmatched}"


def test_the_job_runs_the_support_modules_it_depends_on() -> None:
    names = {path.name for path in _files_the_job_runs()}

    assert {"desktop_release.py", "stand_in_shell_bundle.py", "test_desktop_workflow_triggers.py"} <= names
