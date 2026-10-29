"""Tests for what code_graph_tool tells the model when an answer is cut at the row cap.

[INPUT]
- app.services.code_graph.agent_tool (POS: agent-facing code graph tool and its conditional mount)

[OUTPUT]
- pytest suite: a qualified name returns the same rows as the bare name for the actions that match on the last
  name part, and the row-cap note suggests only what really narrows the answer of that action.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_row_cap_notes.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV

from app.services.code_graph.agent_tool import MAX_ROWS, create_code_graph_tool

_OVER_CAP = MAX_ROWS + 5
_CUT_NOTE = f"More rows exist than the {MAX_ROWS} shown"
# Actions whose cut answer a qualified name really narrows.
_NARROWED_BY_QUALIFIED_NAME = frozenset({"resolve", "importers"})


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(tmp_path / "persistent"))
    root = tmp_path / "ws"
    root.mkdir()
    return root


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _populate(root: Path) -> None:
    """A workspace in which every cappable action has more than ``MAX_ROWS`` rows to return."""
    calls = "\n".join(f"    target({i})" for i in range(_OVER_CAP))
    _write(root, "m.py", f"def target(n):\n    return n\n\ndef big():\n{calls}\n")
    _write(root, "tests/test_m.py", f"from m import target\n\ndef test_all():\n{calls}\n")
    subclasses = "\n".join(f"class Sub{i}(Base):\n    pass\n" for i in range(_OVER_CAP))
    _write(root, "shapes.py", f"class Base:\n    pass\n\n{subclasses}")
    handlers = "\n".join(f"class Handler{i}:\n    def run(self):\n        return {i}\n" for i in range(_OVER_CAP))
    _write(root, "handlers.py", handlers)
    for i in range(_OVER_CAP):
        _write(root, f"imp/m{i}.py", "import pkg\n")


async def _ask(root: Path, action: str, target: str) -> dict[str, object]:
    result = await create_code_graph_tool(root).ainvoke({"action": action, "target": target})
    return cast(dict[str, object], json.loads(str(result["content"])))


def _sites(answer: dict[str, object]) -> list[str]:
    return [row["at"] for row in cast(list[dict[str, str]], answer["rows"])]


@pytest.mark.parametrize(
    ("action", "qualified", "bare"),
    [("callers", "m.target", "target"), ("tests_calling", "m.target", "target"), ("implementors", "shapes.Base", "Base")],
)
async def test_a_qualified_name_returns_the_same_rows_as_the_bare_name(
    workspace: Path, action: str, qualified: str, bare: str
) -> None:
    _populate(workspace)

    by_qualified = await _ask(workspace, action, qualified)
    by_bare = await _ask(workspace, action, bare)

    assert cast(int, by_bare["total"]) > MAX_ROWS
    assert by_qualified["total"] == by_bare["total"]
    assert _sites(by_qualified) == _sites(by_bare)


@pytest.mark.parametrize(
    ("action", "target"),
    [
        ("callers", "target"),
        ("tests_calling", "target"),
        ("implementors", "Base"),
        ("callees", "m.big"),
        ("resolve", "run"),
        ("importers", "pkg"),
    ],
)
async def test_the_row_cap_note_suggests_only_what_narrows_that_action(workspace: Path, action: str, target: str) -> None:
    _populate(workspace)

    answer = await _ask(workspace, action, target)

    assert cast(int, answer["total"]) > MAX_ROWS
    cut_notes = [note for note in cast(list[str], answer["notes"]) if note.startswith(_CUT_NOTE)]
    assert len(cut_notes) == 1
    assert ("use a qualified name to narrow" in cut_notes[0]) == (action in _NARROWED_BY_QUALIFIED_NAME)
