"""Batched first-index writes and serialised runs of CodeGraphService.

[INPUT]
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)
- app.services.code_graph.graph_store::CodeGraphStore (POS: SQLite store of the index)

[OUTPUT]
- pytest suite covering a first index written in batches cut by file count and by source bytes (same rows as one
  write, a single reset, resume after a failure), a reset that spares the files another run stored, and index runs
  that never overlap per database.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_index_batching.py
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from contextlib import closing
from pathlib import Path

import pytest

from app.services.code_graph import service as service_module
from app.services.code_graph.graph_store import CodeGraphStore
from app.services.code_graph.models import ParsedFile
from app.services.code_graph.service import CodeGraphService


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "proj").mkdir()
    return tmp_path / "proj"


_INDEX_TABLES = ("symbols", "calls", "inheritances", "imports", "files")


def _populate(root: Path, count: int) -> None:
    """``count`` modules that each define a base class, a subclass with a method, an import and a call."""
    for number in range(count):
        _write(
            root,
            f"pkg/m{number}.py",
            f"import pkg.m{(number + 1) % count}\n\nclass Base{number}:\n    pass\n\n"
            f"class Child{number}(Base{number}):\n    def run(self):\n        return helper({number})\n",
        )


def _dump(db_path: Path) -> dict[str, list[tuple[object, ...]]]:
    """Every row of every index table, without the autoincrement ids."""
    with closing(sqlite3.connect(db_path)) as conn:
        dump: dict[str, list[tuple[object, ...]]] = {}
        for table in _INDEX_TABLES:
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})") if row[1] != "id"]
            rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
            dump[table] = sorted(rows, key=repr)
        return dump


def _spy_on_writes(
    graph: CodeGraphService, monkeypatch: pytest.MonkeyPatch, fail_on: int | None = None
) -> list[tuple[int, bool]]:
    """Record ``(parsed files, reset)`` of each write to the store; make write number ``fail_on`` raise instead."""
    writes: list[tuple[int, bool]] = []
    real = graph.store.apply_changes

    def apply_changes(*, removed: Iterable[str], parsed: Sequence[ParsedFile], reset: bool = False) -> None:
        writes.append((len(parsed), reset))
        if len(writes) == fail_on:
            raise sqlite3.OperationalError("disk I/O error")
        real(removed=removed, parsed=parsed, reset=reset)

    monkeypatch.setattr(graph.store, "apply_changes", apply_changes)
    return writes


@pytest.mark.parametrize(
    ("count", "expected_writes"),
    [
        pytest.param(5, [(2, True), (2, False), (1, False)], id="last-batch-is-partial"),
        pytest.param(4, [(2, True), (2, False)], id="files-fill-the-batches-exactly"),
        pytest.param(1, [(1, True)], id="fewer-files-than-one-batch"),
    ],
)
def test_a_first_index_written_in_batches_stores_exactly_what_a_single_write_stores(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int, expected_writes: list[tuple[int, bool]]
) -> None:
    _populate(root, count)
    single = CodeGraphService(tmp_path / "single.db")
    single_stats = single.index_directory(root)

    monkeypatch.setattr(service_module, "INDEX_BATCH_FILES", 2)
    batched = CodeGraphService(tmp_path / "batched.db")
    writes = _spy_on_writes(batched, monkeypatch)
    batched_stats = batched.index_directory(root)

    assert writes == expected_writes
    assert _dump(tmp_path / "batched.db") == _dump(tmp_path / "single.db")
    assert batched_stats.updated_files == single_stats.updated_files == count


def test_a_batch_is_also_cut_by_the_source_bytes_it_holds(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate(root, 7)
    file_bytes = (root / "pkg" / "m0.py").stat().st_size
    single = CodeGraphService(tmp_path / "single.db")
    single_stats = single.index_directory(root)

    # Every module has the same size, so three of them add up to exactly the limit and the batch is cut there.
    monkeypatch.setattr(service_module, "INDEX_BATCH_BYTES", 3 * file_bytes)
    batched = CodeGraphService(tmp_path / "batched.db")
    writes = _spy_on_writes(batched, monkeypatch)
    batched_stats = batched.index_directory(root)

    assert writes == [(3, True), (3, False), (1, False)]
    assert _dump(tmp_path / "batched.db") == _dump(tmp_path / "single.db")
    assert batched_stats.updated_files == single_stats.updated_files == 7


def test_leftovers_without_a_file_record_are_cleared_once_not_by_every_batch(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _populate(root, 3)
    db_path = tmp_path / "graph.db"
    graph = CodeGraphService(db_path)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO symbols (qualified_name, name, kind, file_path, line_start, line_end) "
            "VALUES ('gone.helper', 'helper', 'function', 'gone.py', 1, 1)"
        )
    monkeypatch.setattr(service_module, "INDEX_BATCH_FILES", 1)

    stats = graph.index_directory(root)

    assert graph.definition("gone.helper") is None
    assert all(graph.definition(f"pkg.m{number}.Base{number}") for number in range(3))
    assert stats.total_files == 3


def test_a_first_index_that_fails_midway_resumes_without_reparsing_what_it_stored(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _populate(root, 5)
    CodeGraphService(tmp_path / "single.db").index_directory(root)
    monkeypatch.setattr(service_module, "INDEX_BATCH_FILES", 2)
    graph = CodeGraphService(tmp_path / "graph.db")
    real_apply_changes = graph.store.apply_changes
    _spy_on_writes(graph, monkeypatch, fail_on=2)

    with pytest.raises(sqlite3.OperationalError):
        graph.index_directory(root)
    stored = set(graph.store.get_file_fingerprints())
    monkeypatch.setattr(graph.store, "apply_changes", real_apply_changes)
    reparsed: list[str] = []
    real_parse = CodeGraphService._parse

    def parse(root_dir: Path, rel_path: str, fingerprint: tuple[int, int]) -> ParsedFile | None:
        reparsed.append(rel_path)
        return real_parse(root_dir, rel_path, fingerprint)

    monkeypatch.setattr(CodeGraphService, "_parse", staticmethod(parse))
    resumed = graph.index_directory(root)

    assert len(stored) == 2
    assert len(reparsed) == 3 and stored.isdisjoint(reparsed)
    assert resumed.total_files == 5
    assert _dump(tmp_path / "graph.db") == _dump(tmp_path / "single.db")


def test_index_runs_of_one_database_never_overlap_while_other_databases_are_not_held_up(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _populate(root, 1)
    first_parsing, release, second_parsed = threading.Event(), threading.Event(), threading.Event()
    real_parse = CodeGraphService._parse

    def parse(root_dir: Path, rel_path: str, fingerprint: tuple[int, int]) -> ParsedFile | None:
        name = threading.current_thread().name
        if name == "second":
            second_parsed.set()
        if name == "first":
            first_parsing.set()
            release.wait(30)
        return real_parse(root_dir, rel_path, fingerprint)

    monkeypatch.setattr(CodeGraphService, "_parse", staticmethod(parse))
    shared = tmp_path / "shared.db"
    first = threading.Thread(target=lambda: CodeGraphService(shared).index_directory(root), name="first")
    second = threading.Thread(target=lambda: CodeGraphService(shared).index_directory(root), name="second")
    other = threading.Thread(target=lambda: CodeGraphService(tmp_path / "other.db").index_directory(root), name="other")
    try:
        first.start()
        assert first_parsing.wait(10)
        second.start()
        other.start()
        other.join(timeout=3)
        time.sleep(0.2)  # a second run that is not held back would start parsing within this time

        assert not other.is_alive()
        assert not second_parsed.is_set()
    finally:
        release.set()
        for worker in (first, second, other):
            worker.join(timeout=10)

    assert not second_parsed.is_set()  # it found the first run's files already stored
    assert CodeGraphService(shared).index_directory(root).updated_files == 0


def test_a_reset_from_a_run_that_began_on_an_empty_store_keeps_the_files_another_run_stored_since(tmp_path: Path) -> None:
    store = CodeGraphStore(tmp_path / "graph.db")

    def stored(path: str) -> ParsedFile:
        return ParsedFile(file_path=path, mtime_ns=1, size=1, symbols=[], calls=[], inheritances=[], imports=[])

    store.apply_changes(removed=[], parsed=[stored("a.py")], reset=True)
    store.apply_changes(removed=[], parsed=[stored("b.py")], reset=True)

    assert set(store.get_file_fingerprints()) == {"a.py", "b.py"}
