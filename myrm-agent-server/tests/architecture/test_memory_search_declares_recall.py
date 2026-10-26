"""Architecture test: every server call of MemoryManager.search says whether it is a recall."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_ROOT = _SERVER_ROOT / "app"

# The names under which server code holds a MemoryManager.
_MANAGER_NAMES = frozenset({"manager", "memory_manager"})


def _search_calls(source: str) -> list[tuple[int, bool]]:
    """Return (line, declares track_access) for each ``manager.search(...)`` call in the source."""
    calls: list[tuple[int, bool]] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "search"):
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id in _MANAGER_NAMES:
            calls.append((node.lineno, any(keyword.arg == "track_access" for keyword in node.keywords)))
    return calls


def _scan_app() -> tuple[int, list[str]]:
    found = 0
    undeclared: list[str] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        calls = _search_calls(path.read_text(encoding="utf-8"))
        found += len(calls)
        undeclared += [f"{path.relative_to(_SERVER_ROOT).as_posix()}:{line}" for line, declared in calls if not declared]
    return found, undeclared


@pytest.mark.architecture
def test_memory_search_declares_whether_it_is_a_recall() -> None:
    """A search stamps its hits as used and a used memory is protected from forgetting."""
    _, undeclared = _scan_app()
    assert not undeclared, (
        "MemoryManager.search stamps its hits as used by default. Pass track_access=True when the hits "
        "serve a user or an agent, track_access=False for dedup, diagnostics and existence checks:\n" + "\n".join(undeclared)
    )


@pytest.mark.architecture
def test_detector_flags_undeclared_calls_and_sees_the_real_ones() -> None:
    source = (
        "async def f(manager, other):\n"
        "    await manager.search('a')\n"
        "    await manager.search('b', track_access=False)\n"
        "    await other.search('c')\n"
    )
    assert _search_calls(source) == [(2, False), (3, True)]
    assert _scan_app()[0] > 0, (
        "no manager.search call found under app/: the receiver names the scan looks for do not occur in the code"
    )
