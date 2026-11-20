"""Tests for upload_sync: the query injection, the filename sanitizer and the production listing of uploads."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.conversion.chat_context import ChatContext
from app.services.agent.params.enrichment import enrich_query
from app.services.agent.params.enrichment.upload_sync import (
    _sanitize_filename,
    inject_uploaded_files_into_query,
)
from app.services.agent.params.models import AgentRequest

# Above the 100 KB threshold from which a non-image upload is synced into the workspace.
_LARGE_UPLOAD_BYTES = 200 * 1024


class TestInjectUploadedFilesIntoQuery:
    """Tests for inject_uploaded_files_into_query."""

    def test_empty_synced_files_returns_original(self) -> None:
        query = "Hello world"
        result = inject_uploaded_files_into_query(query, [])
        assert result == "Hello world"

    def test_every_file_is_listed_in_one_block_in_the_given_order(self) -> None:
        synced = [("notes.txt", "_uploaded/notes.txt"), ("manual.pdf", "_uploaded/manual.pdf")]

        result = inject_uploaded_files_into_query("Review these", synced)

        assert result == (
            "Review these\n\n"
            "<uploaded_files_in_workspace>\n"
            '  <file name="notes.txt" workspace_path="_uploaded/notes.txt"/>\n'
            '  <file name="manual.pdf" workspace_path="_uploaded/manual.pdf"/>\n'
            "</uploaded_files_in_workspace>"
        )

    def test_names_with_markup_characters_are_quoted(self) -> None:
        result = inject_uploaded_files_into_query("Look", [("a&b<c>.pdf", "_uploaded/ab.pdf")])

        assert isinstance(result, str)
        assert '  <file name="a&amp;b&lt;c&gt;.pdf" workspace_path="_uploaded/ab.pdf"/>' in result

    def test_multimodal_query_appends_to_text_part(self) -> None:
        query = [{"type": "text", "text": "Original question"}]
        synced = [("doc.pdf", "_uploaded/doc.pdf")]

        result = inject_uploaded_files_into_query(query, synced)

        assert isinstance(result, list)
        text_part = result[0]["text"]
        assert "Original question" in text_part
        assert "<uploaded_files_in_workspace>" in text_part


class TestEnrichQueryListsUploads:
    """The production path: what the model receives for an upload, whatever the file's size or type."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["manual.pdf", "report.docx", "deck.pptx", "sheet.xlsx"])
    async def test_a_large_document_is_listed_like_any_other_file(self, tmp_path: Path, name: str) -> None:
        uploaded = tmp_path / "_uploaded"
        uploaded.mkdir()
        (uploaded / name).write_bytes(b"x" * _LARGE_UPLOAD_BYTES)
        request = AgentRequest(message_id="m1", query="Summarize it", uploaded_file_ids=["f1"])

        with patch(
            "app.services.agent.params.enrichment.pipeline.sync_uploaded_files_to_workspace",
            new=AsyncMock(return_value=[(name, f"_uploaded/{name}")]),
        ):
            enriched = await enrich_query(request, ChatContext(chat_workspace_dir=str(tmp_path)), None)

        assert enriched.query == (
            "Summarize it\n\n"
            "<uploaded_files_in_workspace>\n"
            f'  <file name="{name}" workspace_path="_uploaded/{name}"/>\n'
            "</uploaded_files_in_workspace>"
        )


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
