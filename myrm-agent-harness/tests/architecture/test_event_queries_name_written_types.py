"""Architecture gate: an event log query names only event types the logger writes.

A query for a type nothing writes returns an empty list without an error, so the code behind it never runs and no test
that hand-builds the event notices (the skill evolution slice analyzer queried ``pre_tool_use`` for as long as it
existed, while the broadcaster writes ``tool_start``). Every string in an ``event_types=`` argument must be a type
``EventLogger.log`` persists or one of the types the logger writes itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

from myrm_agent_harness.agent.event_log.logger import _SECURITY_AUDIT, _SESSION_END, _SESSION_START
from myrm_agent_harness.agent.event_log.types import get_persistent_event_types

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"


def _queried_types(source: str) -> list[tuple[int, str]]:
    """Every string literal inside an ``event_types=`` argument of ``source``, with its line."""
    queried: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "event_types":
            queried.extend(
                (literal.lineno, literal.value)
                for literal in ast.walk(node.value)
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str)
            )
    return queried


def _unwritten_queries(root: Path) -> list[str]:
    written = get_persistent_event_types() | {_SESSION_START, _SESSION_END, _SECURITY_AUDIT}
    return [
        f"{path.relative_to(root)}:{line} queries {event_type!r}"
        for path in sorted(root.rglob("*.py"))
        for line, event_type in _queried_types(path.read_text(encoding="utf-8"))
        if event_type not in written
    ]


def test_every_event_type_a_query_names_is_written_by_the_logger() -> None:
    assert _unwritten_queries(SRC_ROOT) == []


def test_the_detector_finds_a_query_for_a_type_nothing_writes(tmp_path: Path) -> None:
    (tmp_path / "query.py").write_text(
        "backend.get_events(sid, EventFilter(event_types=frozenset({'pre_tool_use', 'tool_start'})))\n",
        encoding="utf-8",
    )

    assert _unwritten_queries(tmp_path) == ["query.py:1 queries 'pre_tool_use'"]
