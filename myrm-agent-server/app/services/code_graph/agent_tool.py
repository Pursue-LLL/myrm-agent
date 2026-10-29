"""Agent-facing code graph tool: structural navigation over a workspace's Python and TypeScript/JavaScript code.

[INPUT]
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)
- app.services.code_graph.models::IndexStats (POS: state of the index after one run)
- myrm_agent_harness.runtime.paths.execution_paths::get_persistent_root (POS: persistent volume root)

[OUTPUT]
- SKILL_NAME: name of the prebuilt skill whose enablement mounts the tool
- create_code_graph_tool: LangChain tool factory bound to one workspace
- append_code_graph_tool: conditional mount used by the agent factory

[POS]
Conditional business tool. The index lives in the persistent volume, never inside the workspace, and is brought
up to date before every query, so the model never indexes or refreshes anything itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain.tools import tool
from langchain_core.tools import BaseTool
from myrm_agent_harness.runtime.paths.execution_paths import get_persistent_root
from pydantic import BaseModel, Field

from app.services.code_graph.models import IndexStats
from app.services.code_graph.service import CodeGraphService

SKILL_NAME = "repo-call-graph"
MAX_ROWS = 50
_DOC_CHARS = 300
_JS_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")

# What can narrow an answer cut at MAX_ROWS. callers, tests_calling and implementors match on the last name part,
# so a qualified name returns the same rows and only a text search inside a directory narrows them.
_HINT_QUALIFIED_NAME = "use a qualified name to narrow the result."
_HINT_SEARCH = "a qualified name returns the same rows for this action, so search the directory you care about with grep."
_HINT_OPEN_FUNCTION = "they are listed by line number, so open the function to see the rest."

CodeGraphAction = Literal["resolve", "definition", "callers", "callees", "implementors", "importers", "tests_calling"]

_DESCRIPTION = (
    "Navigate Python and TypeScript/JavaScript code in the workspace by structure instead of text search. "
    "One call answers one question; the index refreshes itself first. Actions (target in brackets):\n"
    "- resolve [name, qualified name, or path:line]: matching functions, classes and methods with qualified name and line range. "
    "Start here when you only have a plain name.\n"
    "- definition [qualified name]: kind, location and docstring of one symbol.\n"
    "- callers [function name]: call sites that call it, each with the calling function. match=exact: the call text "
    "equals the target; match=name: only the last name part matches, so it may be another function with the same name. "
    "definitions is how many functions share the name; when it is above 1, treat match=name rows as candidates.\n"
    "- callees [qualified name from resolve]: calls made inside that function, as written at the call site "
    "(not resolved to definitions).\n"
    "- implementors [class name]: classes that extend it.\n"
    "- importers [module name]: Python import statements of that module or anything inside it, with the importing module. "
    "TypeScript/JavaScript imports are not indexed.\n"
    "- tests_calling [function name]: call sites in test files that call it directly; tests that reach it through "
    "other functions are not listed.\n"
    "Rows give file:line. Open the location before editing: JS/TS attribution is approximate and dynamic calls are "
    "not seen. Use grep for plain text, strings and comments."
)


class CodeGraphInput(BaseModel):
    """Input schema for code_graph_tool."""

    action: CodeGraphAction = Field(..., description="What to look up; see the tool description for what each action returns.")
    target: str = Field(
        ...,
        description="The name the action works on: a function, class or module name, a qualified name, or path:line for resolve.",
    )


Row = dict[str, object]


def _span(row: Row) -> str:
    return f"{row['file_path']}:{row['line_start']}-{row['line_end']}"


def _site(row: Row) -> str:
    return f"{row['file_path']}:{row['line']}"


def _call_row(row: Row, **fields: object) -> Row:
    out: Row = {"at": _site(row), **fields, "args": row["arg_count"]}
    if row["kwarg_names"]:
        out["kwargs"] = row["kwarg_names"]
    return out


def _definition_row(row: Row) -> Row:
    out: Row = {"name": row["qualified_name"], "kind": row["kind"], "at": _span(row)}
    doc = str(row["docstring"]).strip()
    if doc:
        out["doc"] = doc[:_DOC_CHARS]
    return out


def _importer_row(row: Row) -> Row:
    out: Row = {"at": _site(row), "importer": row["importer_module"], "imports": row["imported_symbol"]}
    if row["alias"]:
        out["alias"] = row["alias"]
    return out


@dataclass(frozen=True)
class _Action:
    query: Callable[[CodeGraphService, str], list[Row]]
    row: Callable[[Row], Row]
    cut_hint: str


def _definition_query(service: CodeGraphService, target: str) -> list[Row]:
    found = service.definition(target)
    return [found] if found else []


_ACTIONS: dict[str, _Action] = {
    "resolve": _Action(
        lambda s, t: s.resolve(t),
        lambda r: {"name": r["qualified_name"], "kind": r["kind"], "at": _span(r)},
        cut_hint=_HINT_QUALIFIED_NAME,
    ),
    # At most one row, so it is never cut.
    "definition": _Action(_definition_query, _definition_row, cut_hint=""),
    "callers": _Action(
        lambda s, t: s.callers(t),
        lambda r: _call_row(r, caller=r["caller"], callee=r["callee"], match=r["match"]),
        cut_hint=_HINT_SEARCH,
    ),
    "callees": _Action(
        lambda s, t: s.callees(t),
        lambda r: _call_row(r, callee=r["callee"]),
        cut_hint=_HINT_OPEN_FUNCTION,
    ),
    "implementors": _Action(
        lambda s, t: s.implementors(t),
        lambda r: {"class": r["sub_type"], "extends": r["super_type"], "at": _site(r)},
        cut_hint=_HINT_SEARCH,
    ),
    "importers": _Action(lambda s, t: s.importers(t), _importer_row, cut_hint=_HINT_QUALIFIED_NAME),
    "tests_calling": _Action(
        lambda s, t: s.tests_calling(t),
        lambda r: {"at": _site(r), "test": r["test_symbol"], "match": r["match"]},
        cut_hint=_HINT_SEARCH,
    ),
}


def _database_path(workspace_root: Path) -> Path:
    digest = hashlib.sha256(str(workspace_root.resolve()).encode()).hexdigest()[:16]
    return Path(get_persistent_root()) / "code_graph" / f"{digest}.db"


def _notes(shown_rows: list[Row], total: int, definitions: int, stats: IndexStats, cut_hint: str) -> list[str]:
    notes: list[str] = []
    if stats.truncated:
        notes.append(
            "The workspace has more files than the index can list, so part of it is not indexed. "
            "A missing result is unconfirmed: use grep."
        )
    if total == 0:
        notes.append(
            "Nothing found. Names are case-sensitive; try resolve with a shorter name or use grep. "
            "Only Python and TypeScript/JavaScript files are indexed."
        )
    if total > MAX_ROWS:
        notes.append(f"More rows exist than the {MAX_ROWS} shown; {cut_hint}")
    if definitions > 1:
        notes.append(f"{definitions} functions share this name, so match=name rows may call another one.")
    if any(str(row["at"]).rsplit(":", 1)[0].endswith(_JS_TS_SUFFIXES) for row in shown_rows):
        notes.append("JS/TS rows are approximate: the calling function may be wrong, so open the location.")
    if stats.skipped_files:
        notes.append(f"{stats.skipped_files} source files were not indexed (links, oversized, unreadable or not valid Python).")
    return notes


class _Navigator:
    """One workspace's index and the serialised queries against it."""

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root
        self._service: CodeGraphService | None = None
        # Queues the callers of this tool without holding a thread each; index runs are serialised by the service.
        self._lock = asyncio.Lock()

    async def ask(self, action: CodeGraphAction, target: str) -> dict[str, object]:
        if not target.strip():
            return {"content": "target is required.", "metadata": {"error": True, "action": action}}
        async with self._lock:
            try:
                return await asyncio.to_thread(self._ask, action, target.strip())
            except (OSError, sqlite3.Error) as exc:
                return {"content": f"code_graph_tool failed: {exc}", "metadata": {"error": True, "action": action}}

    def _ask(self, action: CodeGraphAction, target: str) -> dict[str, object]:
        if self._service is None:
            self._service = CodeGraphService(_database_path(self._root))
        stats = self._service.index_directory(self._root)
        spec = _ACTIONS[action]
        found = spec.query(self._service, target)
        rows = [spec.row(r) for r in found[:MAX_ROWS]]

        payload: dict[str, object] = {"action": action, "target": target, "total": len(found), "rows": rows}
        definitions = 0
        if action in ("callers", "tests_calling"):
            definitions = self._service.definition_count(target)
            payload["definitions"] = definitions
        notes = _notes(rows, len(found), definitions, stats, spec.cut_hint)
        if notes:
            payload["notes"] = notes
        return {
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "metadata": {"action": action, "total": len(found), "indexed_files": stats.total_files},
        }


def create_code_graph_tool(workspace_root: Path) -> BaseTool:
    """Create code_graph_tool bound to ``workspace_root``."""
    navigator = _Navigator(workspace_root)

    @tool("code_graph_tool", description=_DESCRIPTION, args_schema=CodeGraphInput)
    async def code_graph_tool(action: CodeGraphAction, target: str) -> dict[str, object]:
        return await navigator.ask(action, target)

    return code_graph_tool


def append_code_graph_tool(tools: list[object], *, enabled_prebuilt_ids: frozenset[str], workspace_root: str | None) -> bool:
    """Mount code_graph_tool when the user enabled its skill and the agent has a workspace."""
    if SKILL_NAME not in enabled_prebuilt_ids or not workspace_root:
        return False
    tools.append(create_code_graph_tool(Path(workspace_root)))
    return True
