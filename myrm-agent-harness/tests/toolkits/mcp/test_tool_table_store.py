"""ToolTableStore: one atomic file per connection-pool key; anything unreadable counts as absent.

[INPUT]
- myrm_agent_harness.toolkits.mcp.tool_table_store (POS: unit under test)

[OUTPUT]
- Unit tests for loading, saving, discarding and pruning stored tool tables.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from myrm_agent_harness.infra.data_dir import DATA_DIR_ENV
from myrm_agent_harness.toolkits.mcp import tool_table_store
from myrm_agent_harness.toolkits.mcp.tool_table import TableTool, ToolTable, encode_table
from myrm_agent_harness.toolkits.mcp.tool_table_store import ToolTableStore


def _table(name: str = "search") -> ToolTable:
    tool = TableTool(
        name=name,
        description="Search the index.",
        args_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema=None,
    )
    return ToolTable(tools=(tool,), instructions="Use search first.")


def test_a_saved_table_loads_back_equal(tmp_path: Path) -> None:
    store = ToolTableStore(tmp_path / "tables")

    store.save("abc", _table())

    loaded = store.load("abc")
    assert loaded is not None
    assert encode_table(loaded) == encode_table(_table())


def test_a_missing_table_loads_as_absent(tmp_path: Path) -> None:
    assert ToolTableStore(tmp_path / "never-created").load("abc") is None


@pytest.mark.parametrize(
    "content",
    [b"not json", b'{"version": 999}', b"\xff\xfe\x00invalid utf-8"],
    ids=["invalid-json", "other-layout", "invalid-utf8"],
)
def test_an_unreadable_file_loads_as_absent(tmp_path: Path, content: bytes) -> None:
    (tmp_path / "abc.json").write_bytes(content)

    assert ToolTableStore(tmp_path).load("abc") is None


def test_saving_an_identical_table_writes_nothing_but_refreshes_the_entry(tmp_path: Path) -> None:
    store = ToolTableStore(tmp_path)
    store.save("abc", _table())
    path = tmp_path / "abc.json"
    os.utime(path, (1_000_000, 1_000_000))
    inode = path.stat().st_ino

    store.save("abc", _table())

    assert path.stat().st_ino == inode
    assert path.stat().st_mtime > 1_000_000


def test_saving_a_changed_table_replaces_the_stored_one(tmp_path: Path) -> None:
    store = ToolTableStore(tmp_path)
    store.save("abc", _table("search"))

    store.save("abc", _table("lookup"))

    loaded = store.load("abc")
    assert loaded is not None
    assert [tool.name for tool in loaded.tools] == ["lookup"]
    assert [path.name for path in tmp_path.iterdir()] == ["abc.json"]


def test_a_saved_table_is_private_to_the_user(tmp_path: Path) -> None:
    ToolTableStore(tmp_path).save("abc", _table())

    assert (tmp_path / "abc.json").stat().st_mode & 0o777 == 0o600


def test_discard_removes_the_table_and_tolerates_a_missing_one(tmp_path: Path) -> None:
    store = ToolTableStore(tmp_path)
    store.save("abc", _table())

    store.discard("abc")
    store.discard("abc")

    assert store.load("abc") is None


def test_only_the_newest_entries_are_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_table_store, "_MAX_ENTRIES", 3)
    store = ToolTableStore(tmp_path)
    for index in range(5):
        store.save(f"key{index}", _table(f"tool{index}"))
        os.utime(tmp_path / f"key{index}.json", (1_000 + index, 1_000 + index))

    store.save("key5", _table("tool5"))

    assert sorted(path.stem for path in tmp_path.iterdir()) == ["key3", "key4", "key5"]


def test_the_default_store_lives_under_the_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))

    ToolTableStore.at_state_root().save("abc", _table())

    assert (tmp_path / "cache" / "mcp-tool-tables" / "abc.json").is_file()
