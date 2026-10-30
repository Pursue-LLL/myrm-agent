"""Tests for code_graph_tool: mounting gate, result envelope, freshness, caps and schema stability.

[INPUT]
- app.services.code_graph.agent_tool (POS: agent-facing code graph tool and its conditional mount)
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)

[OUTPUT]
- pytest suite covering the skill/workspace mount gate, match and ambiguity labels, per-call index freshness,
  row caps, empty and failing queries, a call asked again after a cancelled one, index placement outside the
  workspace, and static tool schema.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_agent_tool.py
"""

from __future__ import annotations

import ast
import asyncio
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import cast, get_args

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.api.skills import parse_skill_frontmatter
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV
from myrm_agent_harness.toolkits.filesystem_suggest import WorkspacePathIndexer
from pydantic import BaseModel

from app.services.code_graph.agent_tool import (
    _ACTIONS,
    MAX_ROWS,
    SKILL_NAME,
    CodeGraphAction,
    append_code_graph_tool,
    create_code_graph_tool,
)
from app.services.code_graph.models import ParsedFile
from app.services.code_graph.service import CodeGraphService

Row = dict[str, object]

_SERVER_ROOT = Path(__file__).resolve().parents[3]
_FACTORY = _SERVER_ROOT / "app" / "ai_agents" / "general_agent" / "factory.py"
_SKILL_DIR = _SERVER_ROOT / "assets" / "prebuilt_skills" / SKILL_NAME


@dataclass(frozen=True)
class Answer:
    """A tool result: the parsed JSON payload (or ``{"text": ...}`` for plain-text errors) and its metadata."""

    body: dict[str, object]
    metadata: dict[str, object]

    @property
    def rows(self) -> list[Row]:
        return cast(list[Row], self.body["rows"])

    @property
    def notes(self) -> list[str]:
        return cast(list[str], self.body.get("notes", []))


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _schema(tool: BaseTool) -> dict[str, object]:
    args_schema = tool.args_schema
    assert isinstance(args_schema, type) and issubclass(args_schema, BaseModel)
    return args_schema.model_json_schema()


@pytest.fixture
def persistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "persistent"
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(root))
    return root


@pytest.fixture
def workspace(tmp_path: Path, persistent: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root


async def _ask(tool: BaseTool, action: str, target: str) -> Answer:
    result = await tool.ainvoke({"action": action, "target": target})
    content = str(result["content"])
    try:
        body = json.loads(content)
    except json.JSONDecodeError:
        body = {"text": content}
    return Answer(body=body, metadata=result["metadata"])


def test_tool_mounts_only_when_the_skill_is_enabled_and_a_workspace_exists(tmp_path: Path) -> None:
    for enabled, root in (
        (frozenset(), str(tmp_path)),
        (frozenset({"deep-research"}), str(tmp_path)),
        (frozenset({SKILL_NAME}), None),
    ):
        tools: list[object] = []
        assert append_code_graph_tool(tools, enabled_prebuilt_ids=enabled, workspace_root=root) is False
        assert tools == []

    tools = []
    assert append_code_graph_tool(tools, enabled_prebuilt_ids=frozenset({SKILL_NAME}), workspace_root=str(tmp_path)) is True
    assert [getattr(t, "name", None) for t in tools] == ["code_graph_tool"]


def test_mount_gate_id_is_the_name_of_the_shipped_skill() -> None:
    frontmatter = parse_skill_frontmatter((_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"), SKILL_NAME)

    assert frontmatter.name == SKILL_NAME


def test_agent_factory_mounts_the_tool_with_the_users_enabled_skill_set_and_the_workspace() -> None:
    source = _FACTORY.read_text(encoding="utf-8")
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "append_code_graph_tool"
    ]

    assert [ast.unparse(call) for call in calls] == [
        "append_code_graph_tool(tools, enabled_prebuilt_ids=allowed_prebuilt, workspace_root=workspace_root)"
    ]
    assert "allowed_prebuilt = frozenset(_user_skill_cfg.enabled_prebuilt_ids)" in source


def test_agent_factory_builds_without_the_tool_when_it_cannot_be_loaded() -> None:
    """A native parser that fails to import must cost the agent this tool, not its creation."""
    tree = ast.parse(_FACTORY.read_text(encoding="utf-8"))
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any(
            isinstance(inner, ast.ImportFrom) and inner.module == "app.services.code_graph.agent_tool"
            for stmt in node.body
            for inner in ast.walk(stmt)
        )
    ]

    assert len(guarded) == 1
    assert [ast.unparse(handler.type) for handler in guarded[0].handlers if handler.type] == ["Exception"]


async def test_callers_label_exact_and_name_matches_and_flag_shared_names(workspace: Path) -> None:
    _write(workspace, "a.py", "class A:\n    def save(self):\n        return 1\n")
    _write(workspace, "b.py", "class B:\n    def save(self):\n        return 2\n\ndef run(x):\n    x.save()\n")
    _write(workspace, "c.py", "def helper():\n    return 1\n\ndef go():\n    helper()\n")
    tool = create_code_graph_tool(workspace)

    shared = await _ask(tool, "callers", "save")
    assert shared.body["definitions"] == 2
    assert [row["match"] for row in shared.rows] == ["name"]
    assert any("share this name" in note for note in shared.notes)

    unique = await _ask(tool, "callers", "helper")
    assert unique.body["definitions"] == 1
    assert [(row["caller"], row["match"]) for row in unique.rows] == [("c.go", "exact")]
    assert "notes" not in unique.body


async def test_every_action_answers_from_one_small_project(workspace: Path) -> None:
    _write(workspace, "shapes.py", "class Shape:\n    pass\n\nclass Circle(Shape):\n    def area(self):\n        return 3\n")
    _write(workspace, "app.py", "from shapes import Circle\n\ndef report():\n    return Circle().area()\n")
    _write(workspace, "tests/test_app.py", "from app import report\n\ndef test_report():\n    assert report() == 3\n")
    tool = create_code_graph_tool(workspace)

    resolved = await _ask(tool, "resolve", "area")
    assert resolved.rows == [{"name": "shapes.Circle.area", "kind": "method", "at": "shapes.py:5-6"}]

    defined = await _ask(tool, "definition", "shapes.Circle.area")
    assert defined.rows[0]["at"] == "shapes.py:5-6"

    callees = await _ask(tool, "callees", "app.report")
    assert {row["callee"] for row in callees.rows} == {"Circle", "area"}

    implementors = await _ask(tool, "implementors", "Shape")
    assert implementors.rows == [{"class": "shapes.Circle", "extends": "Shape", "at": "shapes.py:4"}]

    importers = await _ask(tool, "importers", "shapes")
    assert [(row["at"], row["importer"]) for row in importers.rows] == [("app.py:1", "app")]

    tests = await _ask(tool, "tests_calling", "report")
    assert [(row["at"], row["test"], row["match"]) for row in tests.rows] == [
        ("tests/test_app.py:4", "tests.test_app.test_report", "exact")
    ]


async def test_importers_state_that_only_python_imports_are_indexed(workspace: Path) -> None:
    _write(workspace, "web/lib.ts", "export function util() {\n  return 1\n}\n")
    _write(workspace, "web/app.ts", "import { util } from './lib'\n\nexport function run() {\n  return util()\n}\n")
    _write(workspace, "shapes.py", "class Shape:\n    pass\n")
    _write(workspace, "app.py", "from shapes import Shape\n")
    tool = create_code_graph_tool(workspace)

    empty = await _ask(tool, "importers", "web.lib")
    listed = await _ask(tool, "importers", "shapes")
    elsewhere = await _ask(tool, "callers", "util")

    assert empty.rows == []
    assert len(empty.notes) == 1
    assert "Nothing found" in empty.notes[0]
    assert "TypeScript/JavaScript files that import" in empty.notes[0]
    assert "Only Python and TypeScript/JavaScript files are indexed" not in empty.notes[0]
    assert [row["importer"] for row in listed.rows] == ["app"]
    assert listed.notes == [_ACTIONS["importers"].gap]
    assert len(elsewhere.rows) == 1
    assert "notes" not in elsewhere.body


async def test_every_call_sees_files_changed_since_the_previous_call(workspace: Path) -> None:
    _write(workspace, "lib.py", "def work():\n    return 1\n")
    tool = create_code_graph_tool(workspace)
    first = await _ask(tool, "callers", "work")
    assert first.rows == []

    _write(workspace, "use.py", "from lib import work\n\ndef main():\n    work()\n")
    second = await _ask(tool, "callers", "work")

    assert [row["caller"] for row in second.rows] == ["use.main"]
    assert second.metadata["indexed_files"] == 2


async def test_rows_are_capped_and_the_cut_is_reported(workspace: Path) -> None:
    calls = "\n".join(f"    target({i})" for i in range(MAX_ROWS + 10))
    _write(workspace, "m.py", f"def target(n):\n    return n\n\ndef caller():\n{calls}\n")
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "callers", "target")

    assert len(answer.rows) == MAX_ROWS
    assert answer.body["total"] == answer.metadata["total"] == MAX_ROWS + 10
    assert any(f"More rows exist than the {MAX_ROWS} shown" in note for note in answer.notes)


async def test_resolve_reports_when_more_than_the_cap_matches(workspace: Path) -> None:
    classes = "\n".join(f"class Handler{i}:\n    def run(self):\n        return {i}\n" for i in range(MAX_ROWS + 5))
    _write(workspace, "m.py", classes)
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "resolve", "run")

    assert len(answer.rows) == MAX_ROWS
    assert any("More rows exist" in note for note in answer.notes)


async def test_a_cut_file_listing_is_reported_so_a_missing_result_is_not_taken_for_unused_code(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(workspace, "app.py", "def helper():\n    return 1\n")
    tool = create_code_graph_tool(workspace)

    complete = await _ask(tool, "callers", "helper")
    monkeypatch.setattr(WorkspacePathIndexer, "is_truncated", staticmethod(lambda files: True))
    cut = await _ask(tool, "callers", "helper")

    assert not any("more files" in note for note in complete.notes)
    assert any("more files" in note and "grep" in note for note in cut.notes)


async def test_a_target_with_no_match_says_what_to_try_next(workspace: Path) -> None:
    _write(workspace, "m.py", "def present():\n    return 1\n")
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "definition", "absent")

    assert answer.rows == []
    assert any("Nothing found" in note and "grep" in note for note in answer.notes)


async def test_definition_returns_location_and_trimmed_docstring(workspace: Path) -> None:
    _write(workspace, "m.py", 'def documented():\n    """' + "x" * 500 + '"""\n    return 1\n')
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "definition", "m.documented")

    [row] = answer.rows
    assert row["at"] == "m.py:1-3"
    assert len(str(row["doc"])) == 300


async def test_typescript_callers_name_the_enclosing_function_without_an_attribution_warning(workspace: Path) -> None:
    _write(workspace, "web/api.ts", "export function load() {\n  return 1\n}\n\nexport function page() {\n  load()\n}\n")
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "callers", "load")

    [row] = answer.rows
    assert (row["at"], row["caller"], row["match"]) == ("web/api.ts:6", "web.api.page", "exact")
    assert answer.notes == []


async def test_blank_target_is_rejected_before_anything_is_indexed(workspace: Path, persistent: Path) -> None:
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "callers", "   ")

    assert answer.body == {"text": "target is required."}
    assert answer.metadata["error"] is True
    assert not persistent.exists()


async def test_unusable_index_location_becomes_an_error_result_not_an_exception(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(blocker))
    tool = create_code_graph_tool(workspace)

    answer = await _ask(tool, "callers", "anything")

    assert str(answer.body["text"]).startswith("code_graph_tool failed:")
    assert answer.metadata["error"] is True


async def test_the_index_is_kept_outside_the_workspace(workspace: Path, persistent: Path) -> None:
    _write(workspace, "m.py", "def f():\n    return 1\n")
    before = sorted(p.name for p in workspace.rglob("*"))
    tool = create_code_graph_tool(workspace)

    await _ask(tool, "resolve", "f")

    assert sorted(p.name for p in workspace.rglob("*")) == before
    assert list((persistent / "code_graph").glob("*.db"))


def test_action_literal_and_dispatch_table_cannot_drift() -> None:
    assert set(get_args(CodeGraphAction)) == set(_ACTIONS)


def test_schema_and_description_do_not_depend_on_the_workspace(tmp_path: Path) -> None:
    first = create_code_graph_tool(tmp_path / "one")
    second = create_code_graph_tool(tmp_path / "two")

    assert first.description == second.description
    assert _schema(first) == _schema(second)
    assert str(tmp_path) not in first.description


def test_tool_definition_stays_within_its_prompt_budget(tmp_path: Path) -> None:
    tool = create_code_graph_tool(tmp_path)
    definition = tool.description + json.dumps(_schema(tool))

    assert len(definition) <= 2_100


async def test_a_call_asked_again_after_a_cancelled_one_waits_for_the_index_run_still_in_flight(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(workspace, "m.py", "def f():\n    return 1\n\ndef g():\n    f()\n")
    parsing, release = threading.Event(), threading.Event()
    parsed: list[str] = []
    real_parse = CodeGraphService._parse

    def parse(root: Path, rel_path: str, fingerprint: tuple[int, int]) -> ParsedFile | None:
        parsed.append(rel_path)
        parsing.set()
        release.wait(10)
        return real_parse(root, rel_path, fingerprint)

    monkeypatch.setattr(CodeGraphService, "_parse", staticmethod(parse))
    tool = create_code_graph_tool(workspace)
    try:
        first = asyncio.create_task(_ask(tool, "callers", "f"))
        assert await asyncio.to_thread(parsing.wait, 10)
        first.cancel()  # the worker thread of a cancelled call keeps indexing
        with pytest.raises(asyncio.CancelledError):
            await first

        second = asyncio.create_task(_ask(tool, "callers", "f"))
        await asyncio.sleep(0.2)  # a second run that is not held back would start parsing within this time
        assert parsed == ["m.py"]
    finally:
        release.set()

    answer = await second
    assert parsed == ["m.py"]
    assert len(answer.rows) == 1
