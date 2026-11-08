"""The gate workflows' push and pull_request triggers take no path filter.

[INPUT]
- .github/workflows/server-architecture.yml: the filters under its push and pull_request triggers
- .github/workflows/desktop-contracts.yml: the filters under its push and pull_request triggers
- .github/workflows/public-tree-guards.yml: the filters under its push and pull_request triggers

[OUTPUT]
- that neither trigger of any of the three workflows takes a `paths` or `paths-ignore` filter

[POS]
The gates, the contracts and the public-tree guards read files across the repository, and a list of paths stops covering
a file the day a test starts reading it, with the break then surfacing on an unrelated run. The workflows take no list,
and this test keeps it that way; server-architecture.yml runs it with the rest of the directory and desktop-contracts.yml
by path, so an edit confined to the triggers of one workflow still meets it in a run of another.
"""

from __future__ import annotations

from typing import cast

import pytest
import yaml

from tests.support.desktop_release import WORKFLOWS

_GATE_WORKFLOWS = ("server-architecture.yml", "desktop-contracts.yml", "public-tree-guards.yml")
_PATH_FILTERS = frozenset({"paths", "paths-ignore"})

# `on:` -> {event: {"branches": [...], ...}}; YAML 1.1 reads the key `on` as the boolean True, and an event written
# without options (`pull_request:`) as None.
_WorkflowDocument = dict[bool, dict[str, dict[str, list[str]] | None]]


@pytest.mark.parametrize("event", ("push", "pull_request"))
@pytest.mark.parametrize("workflow", _GATE_WORKFLOWS)
def test_a_trigger_takes_no_path_filter(workflow: str, event: str) -> None:
    document = cast("_WorkflowDocument", yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8")))
    taken = _PATH_FILTERS & set(document[True][event] or {})

    assert not taken, f"{workflow}: a {event} taking {sorted(taken)} lets a change skip the job"
