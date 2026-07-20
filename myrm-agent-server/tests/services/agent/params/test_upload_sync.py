"""Tests for upload_sync module: RAG routing and query injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent.params.upload_sync import (
    _RAG_TEXT_THRESHOLD,
    _sanitize_filename,
    _should_use_rag,
    inject_uploaded_files_into_query,
)


class TestShouldUseRag:
    """Tests for _should_use_rag file classification logic."""

    def test_large_pdf_triggers_rag(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        pdf_file = uploaded / "report.pdf"
        pdf_file.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        assert _should_use_rag("report.pdf", "_uploaded/report.pdf", str(tmp_path))

    def test_small_pdf_does_not_trigger_rag(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        pdf_file = uploaded / "small.pdf"
        pdf_file.write_bytes(b"x" * 1024)

        assert not _should_use_rag("small.pdf", "_uploaded/small.pdf", str(tmp_path))

    @pytest.mark.parametrize("ext", [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"])
    def test_supported_extensions(self, ext: str, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        name = f"file{ext}"
        f = uploaded / name
        f.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        assert _should_use_rag(name, f"_uploaded/{name}", str(tmp_path))

    @pytest.mark.parametrize("ext", [".md", ".txt", ".py", ".csv", ".json"])
    def test_unsupported_extensions_never_rag(self, ext: str, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        name = f"file{ext}"
        f = uploaded / name
        f.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        assert not _should_use_rag(name, f"_uploaded/{name}", str(tmp_path))

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert not _should_use_rag("missing.pdf", "_uploaded/missing.pdf", str(tmp_path))

    def test_exactly_at_threshold_not_rag(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        f = uploaded / "exact.pdf"
        f.write_bytes(b"x" * _RAG_TEXT_THRESHOLD)

        assert not _should_use_rag("exact.pdf", "_uploaded/exact.pdf", str(tmp_path))


class TestInjectUploadedFilesIntoQuery:
    """Tests for inject_uploaded_files_into_query routing logic."""

    def test_empty_synced_files_returns_original(self) -> None:
        query = "Hello world"
        result = inject_uploaded_files_into_query(query, [])
        assert result == "Hello world"

    def test_small_files_use_uploaded_files_tag(self) -> None:
        query = "Analyze this"
        synced = [("readme.md", "_uploaded/readme.md")]
        result = inject_uploaded_files_into_query(query, synced)

        assert isinstance(result, str)
        assert "<uploaded_files_in_workspace>" in result
        assert "readme.md" in result
        assert "<large_documents_for_knowledge_base>" not in result

    def test_large_rag_files_use_knowledge_base_tag(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        pdf_file = uploaded / "big_report.pdf"
        pdf_file.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        query = "Summarize this"
        synced = [("big_report.pdf", "_uploaded/big_report.pdf")]
        result = inject_uploaded_files_into_query(query, synced, workspace_dir=str(tmp_path))

        assert isinstance(result, str)
        assert "<large_documents_for_knowledge_base>" in result
        assert 'action="wiki_ingest_then_query"' in result
        assert "Use wiki_ingest_tool" in result
        assert "Do NOT read the entire file" in result

    def test_mixed_files_use_both_tags(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()

        small = uploaded / "notes.txt"
        small.write_bytes(b"x" * 1024)

        large = uploaded / "manual.pdf"
        large.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        synced = [
            ("notes.txt", "_uploaded/notes.txt"),
            ("manual.pdf", "_uploaded/manual.pdf"),
        ]
        result = inject_uploaded_files_into_query(
            "Review these", synced, workspace_dir=str(tmp_path)
        )

        assert "<uploaded_files_in_workspace>" in result
        assert "<large_documents_for_knowledge_base>" in result

    def test_multimodal_query_appends_to_text_part(self, tmp_path: Path) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        f = uploaded / "doc.pdf"
        f.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        query = [{"type": "text", "text": "Original question"}]
        synced = [("doc.pdf", "_uploaded/doc.pdf")]
        result = inject_uploaded_files_into_query(query, synced, workspace_dir=str(tmp_path))

        assert isinstance(result, list)
        text_part = result[0]["text"]
        assert "Original question" in text_part
        assert "<large_documents_for_knowledge_base>" in text_part

    def test_no_html_comments_in_instruction(self, tmp_path: Path) -> None:
        """Verify the instruction uses plain text, not HTML comments."""
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        f = uploaded / "report.pdf"
        f.write_bytes(b"x" * (_RAG_TEXT_THRESHOLD + 1))

        query = "Read this"
        synced = [("report.pdf", "_uploaded/report.pdf")]
        result = inject_uploaded_files_into_query(query, synced, workspace_dir=str(tmp_path))

        assert "<!--" not in result
        assert "-->" not in result
        assert "Use wiki_ingest_tool" in result


class TestSanitizeFilename:
    """Tests for _sanitize_filename security."""

    def test_removes_path_separators(self) -> None:
        assert _sanitize_filename("../../etc/passwd") == "passwd"

    def test_removes_null_bytes(self) -> None:
        assert "\0" not in _sanitize_filename("file\0name.pdf")

    def test_handles_windows_backslash(self) -> None:
        result = _sanitize_filename("C:\\Users\\doc.pdf")
        assert "\\" not in result

    def test_empty_name_returns_unnamed(self) -> None:
        assert _sanitize_filename("") == "unnamed_file"

    def test_normal_filename_unchanged(self) -> None:
        assert _sanitize_filename("report.pdf") == "report.pdf"
