"""Integration: artifacts_ready short_file_id survives processor → FE JSON."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_local_processor_emits_short_file_id_in_artifacts_event() -> None:
    from app.core.artifacts import LocalArtifactProcessor

    processor = LocalArtifactProcessor(chat_id="chat_short_file", api_prefix="/api/v1")

    async def mock_read(path: str) -> bytes:
        _ = path
        return b"# Deliverable"

    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {
                "filename": "report.md",
                "path": "/workspace/report.md",
                "type": "document",
                "short_file_id": "@file_001",
            }
        ],
        "read_content": mock_read,
        "message_id": "msg_short_file",
    }

    mock_file = MagicMock()
    mock_file.id = "file-id-short-001"

    with patch(
        "app.core.storage.service.FilesService.save_file_reference",
        new_callable=AsyncMock,
    ) as mock_save_ref:
        mock_save_ref.return_value = mock_file
        result = await processor.process_artifacts_ready(event)

    assert result is not None
    assert result["type"] == "artifacts"
    data = result["data"]
    assert isinstance(data, list)
    assert len(data) == 1
    artifact = data[0]
    assert artifact["short_file_id"] == "@file_001"
    assert artifact["filename"] == "report.md"
    assert artifact["id"] == "file-id-short-001"


@pytest.mark.asyncio
async def test_local_processor_omits_short_file_id_when_absent() -> None:
    from app.core.artifacts import LocalArtifactProcessor

    processor = LocalArtifactProcessor(chat_id="chat_no_short", api_prefix="/api/v1")

    async def mock_read(path: str) -> bytes:
        _ = path
        return b"content"

    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {
                "filename": "notes.txt",
                "path": "/workspace/notes.txt",
                "type": "document",
            }
        ],
        "read_content": mock_read,
        "message_id": "msg_no_short",
    }

    mock_file = MagicMock()
    mock_file.id = "file-id-no-short"

    with patch(
        "app.core.storage.service.FilesService.save_file_reference",
        new_callable=AsyncMock,
    ) as mock_save_ref:
        mock_save_ref.return_value = mock_file
        result = await processor.process_artifacts_ready(event)

    assert result is not None
    artifact = result["data"][0]
    assert "short_file_id" not in artifact
