"""LocalArtifactProcessor: oversized shareable artifacts emit artifacts events."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.artifacts.processor import MAX_ARTIFACT_SIZE_BYTES


@pytest.mark.asyncio
async def test_local_processor_emits_oversized_shareable_html(tmp_path) -> None:  # noqa: ANN001
    from app.core.artifacts import LocalArtifactProcessor

    report = tmp_path / "report.html"
    oversized = MAX_ARTIFACT_SIZE_BYTES + 1024
    report.write_bytes(b"x" * oversized)

    processor = LocalArtifactProcessor(chat_id="chat_oversized_html", api_prefix="/api/v1")
    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {
                "filename": "report.html",
                "path": "report.html",
                "type": "html",
            }
        ],
        "read_content": AsyncMock(),
        "message_id": "msg_oversized_html",
    }

    mock_file = MagicMock()
    mock_file.id = "file-id-oversized-html"

    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
            return_value=mock_executor,
        ),
        patch(
            "app.core.storage.service.FilesService.save_file_reference",
            new_callable=AsyncMock,
        ) as mock_save_ref,
    ):
        mock_save_ref.return_value = mock_file
        result = await processor.process_artifacts_ready(event)

    assert result is not None
    assert result["type"] == "artifacts"
    data = result["data"]
    assert isinstance(data, list)
    assert len(data) == 1
    artifact = data[0]
    assert artifact["id"] == "file-id-oversized-html"
    assert artifact["filename"] == "report.html"
    assert artifact["size"] == oversized
    assert artifact.get("file_path") is not None
    mock_save_ref.assert_awaited_once()
    assert mock_save_ref.await_args.kwargs["file_size"] == oversized


@pytest.mark.asyncio
async def test_local_processor_skips_oversized_non_shareable(tmp_path) -> None:  # noqa: ANN001
    from app.core.artifacts import LocalArtifactProcessor

    blob = tmp_path / "dump.bin"
    blob.write_bytes(b"x" * (MAX_ARTIFACT_SIZE_BYTES + 1))

    processor = LocalArtifactProcessor(chat_id="chat_oversized_bin", api_prefix="/api/v1")
    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {
                "filename": "dump.bin",
                "path": "dump.bin",
                "type": "other",
            }
        ],
        "read_content": AsyncMock(),
        "message_id": "msg_oversized_bin",
    }

    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
            return_value=mock_executor,
        ),
        patch(
            "app.core.storage.service.FilesService.save_file_reference",
            new_callable=AsyncMock,
        ) as mock_save_ref,
    ):
        result = await processor.process_artifacts_ready(event)

    assert result is None
    mock_save_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_shareable_reaches_deliverable_deep_link(tmp_path) -> None:  # noqa: ANN001
    """processor artifacts event → collect_channel_artifacts → shareable_artifacts."""
    from app.core.artifacts import LocalArtifactProcessor
    from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
        collect_channel_artifacts,
    )
    from app.core.channel_bridge.executor_helpers import StreamAccumulator

    report = tmp_path / "dashboard.html"
    report.write_bytes(b"x" * (MAX_ARTIFACT_SIZE_BYTES + 512))

    processor = LocalArtifactProcessor(chat_id="chat_deliverable", api_prefix="/api/v1")
    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {
                "filename": "dashboard.html",
                "path": "dashboard.html",
                "type": "html",
            }
        ],
        "read_content": AsyncMock(),
        "message_id": "msg_deliverable",
    }

    mock_file = MagicMock()
    mock_file.id = "art-dashboard-001"

    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
            return_value=mock_executor,
        ),
        patch(
            "app.core.storage.service.FilesService.save_file_reference",
            new_callable=AsyncMock,
            return_value=mock_file,
        ),
        patch(
            "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        artifacts_event = await processor.process_artifacts_ready(event)

    assert artifacts_event is not None
    acc = StreamAccumulator()
    collect_channel_artifacts(artifacts_event, acc)

    assert len(acc.shareable_artifacts) == 1
    assert acc.shareable_artifacts[0][0] == "art-dashboard-001"
    assert acc.shareable_artifacts[0][1] == "dashboard.html"
    assert acc.oversized_deliverables == [("dashboard.html", "5.0 MB")]
