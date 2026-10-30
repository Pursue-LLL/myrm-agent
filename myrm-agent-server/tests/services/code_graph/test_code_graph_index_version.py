"""Tests for the index format version in the database file name.

[INPUT]
- app.services.code_graph.agent_tool (POS: agent-facing code graph tool that places and opens the index)
- app.services.code_graph.models::INDEX_FORMAT_VERSION (POS: format version of the persisted index)
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)

[OUTPUT]
- pytest suite covering the version in the database file name, a version change re-parsing files whose fingerprint
  is unchanged, and the removal of this workspace's older databases without touching other workspaces.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_index_version.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV

from app.services.code_graph import agent_tool
from app.services.code_graph.agent_tool import _database_path, _remove_stale_indexes, create_code_graph_tool
from app.services.code_graph.models import INDEX_FORMAT_VERSION, ParsedFile
from app.services.code_graph.service import CodeGraphService


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(tmp_path / "persistent"))
    root = tmp_path / "ws"
    root.mkdir()
    (root / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    return root


async def _resolve(workspace: Path) -> None:
    await create_code_graph_tool(workspace).ainvoke({"action": "resolve", "target": "helper"})


def test_database_name_carries_the_format_version(workspace: Path) -> None:
    assert _database_path(workspace).name.endswith(f".v{INDEX_FORMAT_VERSION}.db")


async def test_a_new_format_version_parses_files_again_whose_fingerprint_is_unchanged(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed: list[str] = []
    original = CodeGraphService._parse

    def counting(root: Path, rel_path: str, fingerprint: tuple[int, int]) -> ParsedFile | None:
        parsed.append(rel_path)
        return original(root, rel_path, fingerprint)

    monkeypatch.setattr(CodeGraphService, "_parse", staticmethod(counting))

    await _resolve(workspace)
    await _resolve(workspace)
    assert parsed == ["util.py"]

    monkeypatch.setattr(agent_tool, "INDEX_FORMAT_VERSION", INDEX_FORMAT_VERSION + 1)
    await _resolve(workspace)

    assert parsed == ["util.py", "util.py"]


async def test_opening_the_index_removes_the_databases_of_other_versions(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _resolve(workspace)
    first = _database_path(workspace)
    assert first.exists()

    monkeypatch.setattr(agent_tool, "INDEX_FORMAT_VERSION", INDEX_FORMAT_VERSION + 1)
    await _resolve(workspace)

    databases = sorted(path.name for path in first.parent.iterdir() if path.suffix == ".db")
    assert databases == [_database_path(workspace).name]


def test_stale_cleanup_keeps_the_current_database_with_its_wal_files_and_other_workspaces(tmp_path: Path) -> None:
    directory = tmp_path / "code_graph"
    directory.mkdir()
    current = directory / "aaaaaaaaaaaaaaaa.v1.db"
    keep = [current.name, f"{current.name}-wal", f"{current.name}-shm", "bbbbbbbbbbbbbbbb.v1.db", "bbbbbbbbbbbbbbbb.db"]
    stale = ["aaaaaaaaaaaaaaaa.db", "aaaaaaaaaaaaaaaa.db-wal", "aaaaaaaaaaaaaaaa.v0.db", "aaaaaaaaaaaaaaaa.v10.db"]
    for name in (*keep, *stale):
        (directory / name).write_text("", encoding="utf-8")

    _remove_stale_indexes(current)

    assert sorted(path.name for path in directory.iterdir()) == sorted(keep)


def test_stale_cleanup_ignores_a_missing_directory(tmp_path: Path) -> None:
    _remove_stale_indexes(tmp_path / "absent" / "aaaaaaaaaaaaaaaa.v1.db")
