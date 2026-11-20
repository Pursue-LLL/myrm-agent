"""Architecture gate: what an MCP server declares about a tool reaches the host through ``judge`` and nowhere else.

A server's hints are its own unverified statements. Three source-level facts keep them from loosening anything:

- the parallel-safety bit has two readers, the conflict gate and the turn ledger;
- only the built-in safety table and ``judge`` may raise a field of a safety record, and ``judge`` raises
  nothing but the parallel-safety bit (``tests/toolkits/mcp/test_annotations.py`` pins its output);
- the field a converted tool carries its declarations in is written by the converter and read back by
  ``recorded_annotations`` only, so no consumer interprets the hints on its own.

A new reader, writer or reader of the field fails here and has to be argued for in the same change.
"""

from __future__ import annotations

import ast
import functools
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_SRC = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"

_PARALLEL_READERS = {
    "agent/middlewares/concurrency/tool_conflict_gate.py",
    "agent/middlewares/concurrency/turn_ledger.py",
}
_RECORD_WRITERS = {"core/security/tool_registry/safety_table.py", "toolkits/mcp/annotations.py"}
_BUILT_IN_TABLE = {"core/security/tool_registry/safety_table.py"}
_DECLARATION_FIELD_USERS = {"toolkits/mcp/annotations.py", "toolkits/mcp/tool_converter.py"}


@functools.cache
def _sources() -> dict[str, str]:
    return {path.relative_to(_SRC).as_posix(): path.read_text(encoding="utf-8") for path in sorted(_SRC.rglob("*.py"))}


def _modules(*needles: str) -> Iterator[tuple[str, ast.Module]]:
    """The source modules whose text mentions one of ``needles``, parsed (the text check spares parsing the rest)."""
    for relative, text in _sources().items():
        if any(needle in text for needle in needles):
            yield relative, ast.parse(text)


def _raises(call: ast.Call, field: str) -> bool:
    """Whether ``call`` passes ``field`` as anything but a literal ``False``."""
    return any(
        keyword.arg == field and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
        for keyword in call.keywords
    )


def test_the_parallel_safety_bit_has_two_readers() -> None:
    readers = {
        relative
        for relative, tree in _modules("is_concurrent_safe")
        if any(
            isinstance(node, ast.Attribute) and node.attr == "is_concurrent_safe" and isinstance(node.ctx, ast.Load)
            for node in ast.walk(tree)
        )
    }

    assert readers == _PARALLEL_READERS


def test_only_the_built_in_table_and_judge_raise_a_safety_record() -> None:
    offenders: list[str] = []
    for relative, tree in _modules("SafetyMetadata("):
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "SafetyMetadata"):
                continue
            if _raises(node, "is_concurrent_safe") and relative not in _RECORD_WRITERS:
                offenders.append(f"{relative}:{node.lineno} raises is_concurrent_safe")
            for field in ("is_read_only", "is_idempotent"):
                if _raises(node, field) and relative not in _BUILT_IN_TABLE:
                    offenders.append(f"{relative}:{node.lineno} raises {field}")

    assert not offenders, "\n".join(offenders)


def test_the_declaration_field_is_written_and_read_in_one_place_each() -> None:
    users = {
        relative
        for relative, tree in _modules("ANNOTATIONS_METADATA_KEY", "mcp_annotations")
        if any(
            (isinstance(node, ast.Name) and node.id == "ANNOTATIONS_METADATA_KEY")
            or (isinstance(node, ast.alias) and node.name == "ANNOTATIONS_METADATA_KEY")
            or (isinstance(node, ast.Constant) and node.value == "mcp_annotations")
            for node in ast.walk(tree)
        )
    }

    assert users == _DECLARATION_FIELD_USERS
