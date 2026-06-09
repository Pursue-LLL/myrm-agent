"""Integration tests for uploaded file workspace sync.

Tests the full pipeline: FilesService upload → sync_uploaded_files_to_workspace → file on disk → inject_uploaded_files_into_query → query with paths.
Uses real FilesService + LocalStorageProvider (no mocks on the critical path).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.storage.service import FilesService
from app.services.agent.params.upload_sync import (
    _SYNC_THRESHOLD_BYTES,
    inject_uploaded_files_into_query,
    sync_uploaded_files_to_workspace,
)


def _make_service(storage_root: str) -> FilesService:
    backend = LocalStorageBackend(base_path=storage_root)
    return FilesService(storage=backend)


@pytest.mark.asyncio
class TestUploadSyncIntegration:
    """Full-pipeline integration: upload → sync → verify disk → inject query."""

    async def test_large_file_synced_to_workspace(self, tmp_path):
        """Upload a large CSV via FilesService, sync to workspace, verify file on disk."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        content = b"id,value\n" + b"row,data\n" * (_SYNC_THRESHOLD_BYTES // 9 + 1)
        assert len(content) > _SYNC_THRESHOLD_BYTES

        uploaded = await svc.upload_file("sales_report.csv", content, "text/csv")
        assert uploaded.id.startswith("file_")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace([uploaded.id], workspace_dir)

        assert len(synced) == 1
        original_name, rel_path = synced[0]
        assert original_name == "sales_report.csv"
        assert rel_path == "_uploaded/sales_report.csv"

        abs_path = os.path.join(workspace_dir, rel_path)
        assert os.path.isfile(abs_path)
        with open(abs_path, "rb") as f:
            assert f.read() == content

    async def test_small_file_not_synced(self, tmp_path):
        """Files under threshold stay in StorageProvider only — not copied to workspace."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        small_content = b"tiny data"
        uploaded = await svc.upload_file("tiny.txt", small_content, "text/plain")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace([uploaded.id], workspace_dir)

        assert synced == []
        assert not os.path.exists(os.path.join(workspace_dir, "_uploaded"))

    async def test_query_injection_after_sync(self, tmp_path):
        """After syncing, inject_uploaded_files_into_query appends XML context to the query."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        content = b"x" * (_SYNC_THRESHOLD_BYTES + 100)
        uploaded = await svc.upload_file("dataset.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace([uploaded.id], workspace_dir)

        query = "Analyze this data and create a chart"
        result = inject_uploaded_files_into_query(query, synced)
        assert isinstance(result, str)
        assert "<uploaded_files_in_workspace>" in result
        assert 'name="dataset.xlsx"' in result
        assert 'workspace_path="_uploaded/dataset.xlsx"' in result
        assert "Analyze this data" in result

    async def test_multiple_files_mixed_sizes(self, tmp_path):
        """Mix of large and small files: only large ones get synced."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        small = await svc.upload_file("config.json", b'{"key":"val"}', "application/json")
        big1 = await svc.upload_file("data1.csv", b"a" * (_SYNC_THRESHOLD_BYTES + 1), "text/csv")
        big2 = await svc.upload_file("data2.csv", b"b" * (_SYNC_THRESHOLD_BYTES + 50), "text/csv")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace(
                [small.id, big1.id, big2.id], workspace_dir
            )

        assert len(synced) == 2
        names = {s[0] for s in synced}
        assert names == {"data1.csv", "data2.csv"}

        for _, rel_path in synced:
            assert os.path.isfile(os.path.join(workspace_dir, rel_path))

    async def test_duplicate_filenames_across_turns(self, tmp_path):
        """Two uploads with the same filename produce distinct workspace files."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        content_v1 = b"v1 " * (_SYNC_THRESHOLD_BYTES // 3 + 1)
        content_v2 = b"v2 " * (_SYNC_THRESHOLD_BYTES // 3 + 1)
        f1 = await svc.upload_file("report.csv", content_v1, "text/csv")
        f2 = await svc.upload_file("report.csv", content_v2, "text/csv")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced1 = await sync_uploaded_files_to_workspace([f1.id], workspace_dir)
            synced2 = await sync_uploaded_files_to_workspace([f2.id], workspace_dir)

        assert len(synced1) == 1
        assert len(synced2) == 1
        assert synced1[0][1] == "_uploaded/report.csv"
        assert synced2[0][1] == "_uploaded/report_1.csv"

        with open(os.path.join(workspace_dir, synced1[0][1]), "rb") as f:
            assert f.read() == content_v1
        with open(os.path.join(workspace_dir, synced2[0][1]), "rb") as f:
            assert f.read() == content_v2

    async def test_nonexistent_file_id_graceful(self, tmp_path):
        """Non-existent file IDs produce empty result without errors."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace(["file_does_not_exist"], workspace_dir)

        assert synced == []

    async def test_multimodal_query_injection(self, tmp_path):
        """Injection into multimodal query appends to the text part."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        content = b"data" * (_SYNC_THRESHOLD_BYTES // 4 + 1)
        uploaded = await svc.upload_file("image_data.csv", content, "text/csv")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace([uploaded.id], workspace_dir)

        multimodal_query = [
            {"type": "text", "text": "Analyze attached data"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR..."}},
        ]
        result = inject_uploaded_files_into_query(multimodal_query, synced)
        assert isinstance(result, list)
        assert "<uploaded_files_in_workspace>" in result[0]["text"]
        assert "Analyze attached data" in result[0]["text"]

    async def test_special_characters_in_filename(self, tmp_path):
        """Filenames with XML-special characters are safely escaped in query injection."""
        storage_root = str(tmp_path / "storage")
        workspace_dir = str(tmp_path / "workspace")
        os.makedirs(workspace_dir)

        svc = _make_service(storage_root)
        content = b"x" * (_SYNC_THRESHOLD_BYTES + 1)
        uploaded = await svc.upload_file('data "file" <2024>.csv', content, "text/csv")

        from unittest.mock import patch

        with patch("app.core.storage.files_service", svc):
            synced = await sync_uploaded_files_to_workspace([uploaded.id], workspace_dir)

        assert len(synced) == 1
        result = inject_uploaded_files_into_query("analyze", synced)
        assert "&lt;" in result
        assert "&gt;" in result
