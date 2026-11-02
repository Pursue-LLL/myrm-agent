"""Tests for what code_graph_tool tells the model when an answer is cut at the row cap.

[INPUT]
- app.services.code_graph.agent_tool (POS: agent-facing code graph tool and its conditional mount)

[OUTPUT]
- pytest suite: a qualified name returns the same rows as the bare name for the actions that match on the last
  name part, a longer name really narrows resolve and importers, a cut answer of every action counts all its matches
  and says how many of them each file holds, callers and tests_calling list match=exact rows first except for an
  unqualified name that only methods define (match=name rows first), and the row-cap note of every action carries the
  hint that is true for that action.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_row_cap_notes.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV

from app.services.code_graph.agent_tool import MAX_DISTRIBUTION_FILES, MAX_ROWS, create_code_graph_tool

_OVER_CAP = MAX_ROWS + 5
_CUT_NOTE = f"More rows exist than the {MAX_ROWS} shown"
_QUALIFIED_NAME_HINT = "use a qualified name to narrow"


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
    _write(root, "imp/sub.py", "import pkg.sub\n")


async def _ask(root: Path, action: str, query: str) -> dict[str, object]:
    result = await create_code_graph_tool(root).ainvoke({"action": action, "query": query})
    return cast(dict[str, object], json.loads(str(result["content"])))


def _total(answer: dict[str, object]) -> int:
    return cast(int, answer["total"])


def _sites(answer: dict[str, object]) -> list[str]:
    return [row["at"] for row in cast(list[dict[str, str]], answer["rows"])]


def _by_file(answer: dict[str, object]) -> dict[str, int]:
    return cast(dict[str, int], answer["by_file"])


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

    assert _total(by_bare) > MAX_ROWS
    assert _total(by_qualified) == _total(by_bare)
    assert _sites(by_qualified) == _sites(by_bare)


@pytest.mark.parametrize(
    ("action", "qualified", "bare"),
    [("resolve", "handlers.Handler3.run", "run"), ("importers", "pkg.sub", "pkg")],
)
async def test_a_longer_name_brings_resolve_and_importers_under_the_cap(
    workspace: Path, action: str, qualified: str, bare: str
) -> None:
    _populate(workspace)

    narrowed = await _ask(workspace, action, qualified)
    broad = await _ask(workspace, action, bare)

    assert _total(narrowed) <= MAX_ROWS < _total(broad)


# Every action that can be cut: its query, how many rows match, and how many files hold those rows.
_CUT_ANSWERS = [
    ("callers", "target", 2 * _OVER_CAP, 2),
    ("tests_calling", "target", _OVER_CAP, 1),
    ("implementors", "Base", _OVER_CAP, 1),
    ("callees", "m.big", _OVER_CAP, 1),
    ("resolve", "run", _OVER_CAP, 1),
    ("importers", "pkg", _OVER_CAP + 1, _OVER_CAP + 1),
]


@pytest.mark.parametrize(("action", "query", "matches", "files"), _CUT_ANSWERS)
async def test_a_cut_answer_counts_every_match_and_says_how_many_each_file_holds(
    workspace: Path, action: str, query: str, matches: int, files: int
) -> None:
    _populate(workspace)

    answer = await _ask(workspace, action, query)

    assert _total(answer) == matches
    assert len(cast(list[object], answer["rows"])) == MAX_ROWS
    assert len(_by_file(answer)) == min(files, MAX_DISTRIBUTION_FILES)
    assert answer.get("more_files", 0) == max(0, files - MAX_DISTRIBUTION_FILES)
    if files <= MAX_DISTRIBUTION_FILES:
        assert sum(_by_file(answer).values()) == matches


@pytest.mark.parametrize(
    ("action", "query", "hint"),
    [
        ("callers", "target", "returns the same rows"),
        ("tests_calling", "target", "returns the same rows"),
        ("implementors", "Base", "returns the same rows"),
        ("callees", "m.big", "open the function"),
        ("resolve", "run", _QUALIFIED_NAME_HINT),
        ("importers", "pkg", _QUALIFIED_NAME_HINT),
    ],
)
async def test_the_row_cap_note_carries_the_hint_that_is_true_for_that_action(
    workspace: Path, action: str, query: str, hint: str
) -> None:
    _populate(workspace)

    answer = await _ask(workspace, action, query)

    assert _total(answer) > MAX_ROWS
    cut_notes = [note for note in cast(list[str], answer["notes"]) if note.startswith(_CUT_NOTE)]
    assert len(cut_notes) == 1
    assert hint in cut_notes[0]
    assert (_QUALIFIED_NAME_HINT in cut_notes[0]) == (hint == _QUALIFIED_NAME_HINT)


async def test_a_cut_answer_counts_every_match_per_file_and_names_the_files_it_leaves_out(workspace: Path) -> None:
    _populate(workspace)
    for i in range(12):
        _write(workspace, f"extra/user{i:02d}.py", "from m import target\n\ndef use():\n    target(0)\n")

    answer = await _ask(workspace, "callers", "target")

    assert _total(answer) == 2 * _OVER_CAP + 12
    assert list(_by_file(answer).items()) == [("m.py", _OVER_CAP), ("tests/test_m.py", _OVER_CAP)] + [
        (f"extra/user{i:02d}.py", 1) for i in range(8)
    ]
    assert answer["more_files"] == 4
    assert f"by_file counts all {_total(answer)}" in cast(list[str], answer["notes"])[0]


async def test_a_cut_answer_with_few_files_lists_them_all_without_a_remainder(workspace: Path) -> None:
    _populate(workspace)

    answer = await _ask(workspace, "callers", "target")

    assert _by_file(answer) == {"m.py": _OVER_CAP, "tests/test_m.py": _OVER_CAP}
    assert "more_files" not in answer


async def test_an_answer_within_the_cap_carries_no_distribution(workspace: Path) -> None:
    _write(workspace, "m.py", "def target():\n    return 1\n\ndef go():\n    target()\n")

    answer = await _ask(workspace, "callers", "target")

    assert "by_file" not in answer
    assert "more_files" not in answer


_FUNCTION = "def target(n):\n    return n\n"
_METHOD = "class Holder:\n    def target(self):\n        return 1\n"


def _write_call_sites(root: Path, exact_call: str) -> None:
    """The calls of ``target`` in path order: 10 with a receiver, 2 written ``exact_call``, then the other 45.

    The exact rows sit between the name rows, so path order, exact-first and name-first each give a different window."""
    for rel, call, count in (
        ("tests/test_a_receiver.py", "other.target(1)", 10),
        ("tests/test_m_exact.py", exact_call, 2),
        ("tests/test_z_receiver.py", "other.target(1)", _OVER_CAP - 10),
    ):
        body = "\n".join(f"    {call}" for _ in range(count))
        _write(root, rel, f"def test_calls(other):\n{body}\n")


@pytest.mark.parametrize("action", ["callers", "tests_calling"])
@pytest.mark.parametrize(
    ("definitions", "query", "count", "name_first"),
    [
        pytest.param(_FUNCTION, "target", 1, False, id="function"),
        pytest.param("class target:\n    pass\n", "target", 1, False, id="class"),
        pytest.param("", "target", 0, False, id="no definition"),
        pytest.param(f"{_FUNCTION}\n{_METHOD}", "target", 2, False, id="function and method"),
        pytest.param(_METHOD, "target", 1, True, id="methods only"),
        pytest.param(_METHOD, "Holder.target", 1, False, id="methods only, qualified name"),
    ],
)
async def test_exact_rows_are_listed_first_except_for_an_unqualified_name_only_methods_define(
    workspace: Path, action: str, definitions: str, query: str, count: int, name_first: bool
) -> None:
    _write_call_sites(workspace, f"{query}(1)")
    if definitions:
        _write(workspace, "z_lib.py", definitions)

    answer = await _ask(workspace, action, query)

    matches = [row["match"] for row in cast(list[dict[str, str]], answer["rows"])]
    assert _total(answer) == _OVER_CAP + 2
    assert answer["definitions"] == count
    if name_first:
        assert set(matches) == {"name"}
    else:
        assert matches[:2] == ["exact", "exact"]
        assert set(matches[2:]) == {"name"}
