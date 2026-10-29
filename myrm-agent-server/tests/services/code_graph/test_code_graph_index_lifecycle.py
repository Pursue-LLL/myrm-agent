"""Index lifecycle tests for CodeGraphService: idempotent, incremental, and safe about what it reads.

[INPUT]
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)

[OUTPUT]
- pytest suite covering re-indexing an unchanged directory, deleted and changed files, same-named files in different
  directories, git-ignore aware file listing, symlink and size limits, and call-site match labels.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_index_lifecycle.py
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.services.code_graph import service as service_module
from app.services.code_graph.ast_extractor import PythonAstExtractor
from app.services.code_graph.service import CodeGraphService


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "proj").mkdir()
    return tmp_path / "proj"


@pytest.fixture
def graph(tmp_path: Path) -> CodeGraphService:
    return CodeGraphService(tmp_path / "graph.db")


def test_reindexing_an_unchanged_directory_changes_nothing(root: Path, graph: CodeGraphService) -> None:
    _write(root, "a.py", "def alpha():\n    return 1\n")
    _write(root, "b.py", "import a\n\ndef beta():\n    return a.alpha()\n")

    first = graph.index_directory(root)
    second = graph.index_directory(root)
    third = graph.index_directory(root)

    assert (first.updated_files, second.updated_files, third.updated_files) == (2, 0, 0)
    assert (third.total_files, third.total_symbols, third.total_calls) == (first.total_files, first.total_symbols, 1)
    assert len(graph.callers("a.alpha")) == 1
    assert len(graph.callees("b.beta")) == 1


def test_a_deleted_file_leaves_no_symbols_or_call_edges(root: Path, graph: CodeGraphService) -> None:
    _write(root, "a.py", "def alpha():\n    return 1\n")
    _write(root, "b.py", "import a\n\ndef beta():\n    return a.alpha()\n")
    graph.index_directory(root)

    (root / "a.py").unlink()
    stats = graph.index_directory(root)

    assert (stats.removed_files, stats.updated_files, stats.total_files) == (1, 0, 1)
    assert graph.resolve("alpha") == []
    assert graph.definition("a.alpha") is None


def test_a_changed_file_is_replaced_and_a_new_file_is_found_immediately(root: Path, graph: CodeGraphService) -> None:
    _write(root, "svc.py", "def core():\n    return 1\n\ndef old_caller():\n    return core()\n")
    graph.index_directory(root)

    _write(root, "svc.py", "def core():\n    return 1\n\ndef new_caller_with_a_longer_name():\n    return core()\n")
    _write(root, "extra.py", "def extra():\n    return core()\n")
    stats = graph.index_directory(root)

    assert (stats.updated_files, stats.removed_files) == (2, 0)
    assert {c["caller"] for c in graph.callers("core")} == {"svc.new_caller_with_a_longer_name", "extra.extra"}


def test_a_store_without_file_records_is_rebuilt_from_the_directory(root: Path, tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    legacy = CodeGraphService(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO symbols VALUES ('ghost.fn', 'fn', 'function', 'ghost.py', 1, 2, '', '')")
    _write(root, "real.py", "def real():\n    return 1\n")

    legacy.index_directory(root)

    assert legacy.resolve("fn") == []
    assert legacy.definition("real.real") is not None


def test_same_named_typescript_files_in_different_directories_keep_their_symbols(root: Path, graph: CodeGraphService) -> None:
    _write(root, "web/index.ts", "export function render(a: string) {\n  return a;\n}\n")
    _write(root, "admin/index.ts", "export function render(a: string) {\n  return a;\n}\n")

    graph.index_directory(root)

    assert {r["qualified_name"] for r in graph.resolve("render")} == {"web.index.render", "admin.index.render"}
    assert graph.definition_count("render") == 2


def test_the_file_list_follows_gitignore_and_includes_untracked_files(root: Path, graph: CodeGraphService) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    _write(root, ".gitignore", "generated/\n")
    _write(root, "kept.py", "def kept():\n    return 1\n")
    _write(root, "generated/skipped.py", "def skipped():\n    return 1\n")

    stats = graph.index_directory(root)

    assert stats.total_files == 1
    assert graph.resolve("kept") != [] and graph.resolve("skipped") == []


def test_links_and_oversized_files_are_skipped_and_counted(
    root: Path, tmp_path: Path, graph: CodeGraphService, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("def secret_outside():\n    return 1\n", encoding="utf-8")
    _write(root, "ok.py", "def ok():\n    return 1\n")
    (root / "link.py").symlink_to(outside)
    _write(root, "big.py", "def big():\n    return 1\n" + "# padding\n" * 50)
    monkeypatch.setattr(service_module, "MAX_SOURCE_BYTES", 100)

    stats = graph.index_directory(root)

    assert (stats.total_files, stats.skipped_files) == (1, 2)
    assert graph.resolve("secret_outside") == [] and graph.resolve("big") == []


def test_a_file_that_cannot_be_parsed_is_skipped_and_the_run_continues(
    root: Path, graph: CodeGraphService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(root, "good.py", "def good():\n    return 1\n")
    _write(root, "bad.py", "def bad():\n    return 1\n")
    original = PythonAstExtractor.extract

    def extract(self: PythonAstExtractor) -> None:
        if self.file_path == "bad.py":
            raise ValueError("source code string cannot contain null bytes")
        original(self)

    monkeypatch.setattr(PythonAstExtractor, "extract", extract)

    stats = graph.index_directory(root)

    assert (stats.total_files, stats.skipped_files) == (1, 1)
    assert graph.definition("good.good") is not None


def test_callers_say_whether_the_call_text_matches_exactly_or_only_by_name(root: Path, graph: CodeGraphService) -> None:
    _write(root, "pkg/mod.py", "def helper():\n    return 1\n")
    _write(root, "pkg/use.py", "import pkg.mod\n\ndef run(other):\n    pkg.mod.helper()\n    other.helper()\n")
    graph.index_directory(root)

    rows = graph.callers("pkg.mod.helper")

    assert [(r["line"], r["callee"], r["match"]) for r in rows] == [
        (4, "pkg.mod.helper", "exact"),
        (5, "other.helper", "name"),
    ]
    assert graph.definition_count("pkg.mod.helper") == 1


def test_tests_are_recognised_by_path_convention_not_by_substring(root: Path, graph: CodeGraphService) -> None:
    _write(root, "lib/target.py", "def target():\n    return 1\n")
    _write(root, "app/latest_version.py", "from lib.target import target\n\ndef check():\n    return target()\n")
    _write(root, "app/contest/run.py", "from lib.target import target\n\ndef go():\n    return target()\n")
    _write(root, "tests/test_target.py", "from lib.target import target\n\ndef test_it():\n    assert target()\n")
    _write(root, "web/target.spec.ts", "export function specIt() {\n  target();\n}\n")
    graph.index_directory(root)

    calling = graph.tests_calling("target")

    assert {(r["file_path"], r["test_symbol"]) for r in calling} == {
        ("tests/test_target.py", "tests.test_target.test_it"),
        ("web/target.spec.ts", "web.target.spec.specIt"),
    }


def test_names_match_literally_so_underscores_and_percent_signs_are_not_wildcards(root: Path, graph: CodeGraphService) -> None:
    _write(root, "m.py", "def get_user():\n    return 1\n\ndef run(o):\n    o.get_user()\n    o.getXuser()\n    o.getuser()\n")
    graph.index_directory(root)

    assert [r["callee"] for r in graph.callers("get_user")] == ["o.get_user"]
    assert graph.callers("%") == []
    assert graph.resolve("get%") == []
