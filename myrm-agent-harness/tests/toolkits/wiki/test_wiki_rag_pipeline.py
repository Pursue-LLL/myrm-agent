"""Tests for Local RAG pipeline: indexer raw text and compiler enqueue."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.wiki.pipeline.compiler import WikiCompiler


class TestIndexRawText:
    """Tests for WikiIndexer.index_raw_text FTS5 interim indexing."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> Iterator[Path]:
        path = tmp_path / "test_wiki.db"
        yield path

    def _create_fts_table(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
                    concept_name,
                    truth_content
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def test_index_raw_text_inserts_with_raw_prefix(self, db_path: Path) -> None:
        self._create_fts_table(db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("raw:test_doc", "Hello world test content"),
            )
            conn.execute("DELETE FROM wiki_fts WHERE concept_name = ?", ("raw:test_doc",))
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("raw:test_doc", "Hello world test content"),
            )
            cursor = conn.execute(
                "SELECT concept_name, truth_content FROM wiki_fts WHERE concept_name = ?",
                ("raw:test_doc",),
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "raw:test_doc"
            assert "Hello world" in rows[0][1]
        finally:
            conn.close()

    def test_raw_entry_truncates_large_text(self, db_path: Path) -> None:
        self._create_fts_table(db_path)
        large_text = "a" * 10000

        preview = large_text[:5000]
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("raw:large_doc", preview),
            )
            cursor = conn.execute(
                "SELECT truth_content FROM wiki_fts WHERE concept_name = ?",
                ("raw:large_doc",),
            )
            row = cursor.fetchone()
            assert row is not None
            assert len(row[0]) == 5000
        finally:
            conn.close()

    def test_upsert_removes_raw_entry(self, db_path: Path) -> None:
        """When compiled version upserts, raw: entry should be deleted."""
        self._create_fts_table(db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("raw:doc1", "raw content"),
            )
            conn.execute("DELETE FROM wiki_fts WHERE concept_name = ?", ("doc1",))
            conn.execute("DELETE FROM wiki_fts WHERE concept_name = ?", ("raw:doc1",))
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("doc1", "compiled truth content"),
            )
            raw_cursor = conn.execute("SELECT * FROM wiki_fts WHERE concept_name = ?", ("raw:doc1",))
            assert raw_cursor.fetchone() is None

            compiled_cursor = conn.execute("SELECT truth_content FROM wiki_fts WHERE concept_name = ?", ("doc1",))
            row = compiled_cursor.fetchone()
            assert row is not None
            assert "compiled truth" in row[0]
        finally:
            conn.close()

    def test_fts5_search_finds_raw_entries(self, db_path: Path) -> None:
        self._create_fts_table(db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO wiki_fts (concept_name, truth_content) VALUES (?, ?)",
                ("raw:kubernetes_guide", "Kubernetes pod deployment scaling strategies"),
            )
            cursor = conn.execute(
                "SELECT concept_name, rank FROM wiki_fts WHERE wiki_fts MATCH ?",
                ("kubernetes",),
            )
            results = cursor.fetchall()
            assert len(results) >= 1
            assert any("raw:kubernetes_guide" in r[0] for r in results)
        finally:
            conn.close()


def _compiler_with(queue: MagicMock, indexer: MagicMock | None) -> WikiCompiler:
    """A WikiCompiler wired to a mock queue and indexer; ``__new__`` skips the real constructor."""
    compiler = WikiCompiler.__new__(WikiCompiler)
    compiler._queue = queue
    compiler._indexer = indexer
    return compiler


class TestCompilerEnqueueRawIndex:
    """Tests for compiler.enqueue_file triggering raw FTS5 indexing."""

    def test_enqueue_calls_index_raw_text_for_md_files(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test_doc.md"
        md_file.write_text("# Test Document\nSome content here.", encoding="utf-8")

        mock_indexer = MagicMock()
        mock_queue = MagicMock()
        compiler = _compiler_with(mock_queue, mock_indexer)

        with patch.object(compiler, "start_background_worker"):
            compiler.enqueue_file(md_file)

        mock_queue.add_item.assert_called_once_with(md_file)
        mock_indexer.index_raw_text.assert_called_once_with(
            "test_doc",
            "# Test Document\nSome content here.",
        )

    def test_enqueue_skips_indexing_for_non_md_files(self, tmp_path: Path) -> None:
        py_file = tmp_path / "script.py"
        py_file.write_text("print('hello')", encoding="utf-8")

        mock_indexer = MagicMock()
        mock_queue = MagicMock()
        compiler = _compiler_with(mock_queue, mock_indexer)

        with patch.object(compiler, "start_background_worker"):
            compiler.enqueue_file(py_file)

        mock_queue.add_item.assert_called_once()
        mock_indexer.index_raw_text.assert_not_called()

    def test_enqueue_skips_indexing_when_no_indexer(self, tmp_path: Path) -> None:
        md_file = tmp_path / "doc.md"
        md_file.write_text("content", encoding="utf-8")

        mock_queue = MagicMock()
        compiler = _compiler_with(mock_queue, None)

        with patch.object(compiler, "start_background_worker"):
            compiler.enqueue_file(md_file)

        mock_queue.add_item.assert_called_once()

    def test_enqueue_handles_empty_md_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "empty.md"
        md_file.write_text("   \n  ", encoding="utf-8")

        mock_indexer = MagicMock()
        compiler = _compiler_with(MagicMock(), mock_indexer)

        with patch.object(compiler, "start_background_worker"):
            compiler.enqueue_file(md_file)

        mock_indexer.index_raw_text.assert_not_called()
