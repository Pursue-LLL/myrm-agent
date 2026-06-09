"""Tests for app.services.agent.params.upload_sync.

Verifies uploaded file workspace sync and query injection logic.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.upload_sync import (
    _SYNC_THRESHOLD_BYTES,
    _sanitize_filename,
    inject_uploaded_files_into_query,
    sync_uploaded_files_to_workspace,
)


class TestSyncUploadedFilesToWorkspace:
    """Tests for sync_uploaded_files_to_workspace."""

    @pytest.mark.asyncio
    async def test_skips_small_files(self):
        """Files under threshold should not be copied."""
        from app.core.storage.models import File, FilePurpose

        small_file = File(
            id="file_small",
            purpose=FilePurpose.UPLOAD,
            filename="tiny.csv",
            content_type="text/csv",
            size=1024,
            storage_path="uploads/file_small/tiny.csv",
        )

        mock_svc = AsyncMock()
        mock_svc.get_file = AsyncMock(return_value=small_file)
        with patch("app.core.storage.files_service", mock_svc):
            workspace = tempfile.mkdtemp()
            result = await sync_uploaded_files_to_workspace(["file_small"], workspace)

        assert result == []
        assert not os.path.exists(os.path.join(workspace, "_uploaded"))

    @pytest.mark.asyncio
    async def test_copies_large_file(self):
        """Files exceeding threshold should be copied to _uploaded/."""
        from app.core.storage.models import File, FilePurpose

        content = b"x" * (_SYNC_THRESHOLD_BYTES + 1)
        large_file = File(
            id="file_big",
            purpose=FilePurpose.UPLOAD,
            filename="big_data.csv",
            content_type="text/csv",
            size=len(content),
            storage_path="uploads/file_big/big_data.csv",
        )

        mock_svc = AsyncMock()
        mock_svc.get_file = AsyncMock(return_value=large_file)
        mock_svc.get_file_content_by_path = AsyncMock(return_value=content)
        with patch("app.core.storage.files_service", mock_svc):
            workspace = tempfile.mkdtemp()
            result = await sync_uploaded_files_to_workspace(["file_big"], workspace)

        assert len(result) == 1
        filename, rel_path = result[0]
        assert filename == "big_data.csv"
        assert rel_path == "_uploaded/big_data.csv"
        dest = os.path.join(workspace, rel_path)
        assert os.path.isfile(dest)
        with open(dest, "rb") as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_skips_missing_file(self):
        """Missing file IDs should be silently skipped."""
        mock_svc = AsyncMock()
        mock_svc.get_file = AsyncMock(return_value=None)
        with patch("app.core.storage.files_service", mock_svc):
            workspace = tempfile.mkdtemp()
            result = await sync_uploaded_files_to_workspace(["file_ghost"], workspace)

        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicates_filenames(self):
        """Duplicate filenames across turns should not overwrite each other."""
        from app.core.storage.models import File, FilePurpose

        content = b"y" * (_SYNC_THRESHOLD_BYTES + 1)
        file_meta = File(
            id="file_dup",
            purpose=FilePurpose.UPLOAD,
            filename="report.csv",
            content_type="text/csv",
            size=len(content),
            storage_path="uploads/file_dup/report.csv",
        )

        workspace = tempfile.mkdtemp()
        uploaded_dir = os.path.join(workspace, "_uploaded")
        os.makedirs(uploaded_dir)
        with open(os.path.join(uploaded_dir, "report.csv"), "w") as f:
            f.write("old data")

        mock_svc = AsyncMock()
        mock_svc.get_file = AsyncMock(return_value=file_meta)
        mock_svc.get_file_content_by_path = AsyncMock(return_value=content)
        with patch("app.core.storage.files_service", mock_svc):
            result = await sync_uploaded_files_to_workspace(["file_dup"], workspace)

        assert len(result) == 1
        _, rel_path = result[0]
        assert rel_path == "_uploaded/report_1.csv"
        assert os.path.isfile(os.path.join(workspace, "_uploaded", "report.csv"))
        assert os.path.isfile(os.path.join(workspace, rel_path))


class TestInjectUploadedFilesIntoQuery:
    """Tests for inject_uploaded_files_into_query."""

    def test_string_query(self):
        synced = [("data.csv", "_uploaded/data.csv")]
        result = inject_uploaded_files_into_query("Analyze this", synced)
        assert isinstance(result, str)
        assert "<uploaded_files_in_workspace>" in result
        assert 'workspace_path="_uploaded/data.csv"' in result

    def test_empty_synced_noop(self):
        result = inject_uploaded_files_into_query("Hello", [])
        assert result == "Hello"

    def test_multimodal_query(self):
        query = [
            {"type": "text", "text": "Check the data"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}},
        ]
        synced = [("report.xlsx", "_uploaded/report.xlsx")]
        result = inject_uploaded_files_into_query(query, synced)
        assert isinstance(result, list)
        assert "<uploaded_files_in_workspace>" in result[0]["text"]


class TestSanitizeFilename:
    def test_strips_path_separators(self):
        assert _sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_null_bytes(self):
        assert _sanitize_filename("file\0name.csv") == "filename.csv"

    def test_empty_becomes_unnamed(self):
        assert _sanitize_filename("") == "unnamed_file"

    def test_normal_filename_unchanged(self):
        assert _sanitize_filename("my_data.csv") == "my_data.csv"
