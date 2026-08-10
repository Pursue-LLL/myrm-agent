"""Processor upsert-emit consistency: failed DB upsert must not emit artifacts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.artifacts.processor import MAX_ARTIFACT_SIZE_BYTES


@pytest.mark.asyncio
async def test_upsert_failure_does_not_emit_artifact(tmp_path) -> None:  # noqa: ANN001
    from app.core.artifacts import LocalArtifactProcessor

    report = tmp_path / "report.html"
    report.write_bytes(b"x" * (MAX_ARTIFACT_SIZE_BYTES + 512))

    processor = LocalArtifactProcessor(chat_id="chat_upsert_fail", api_prefix="/api/v1")
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
        "message_id": "msg_upsert_fail",
    }

    mock_file = MagicMock()
    mock_file.id = "file-upsert-fail"

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
        patch(
            "app.core.artifacts.listener.upsert_processor_artifact",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db unavailable"),
        ),
    ):
        mock_save_ref.return_value = mock_file
        result = await processor.process_artifacts_ready(event)

    assert result is None
    mock_save_ref.assert_awaited_once()


@pytest.mark.asyncio
async def test_partial_upsert_failure_emits_only_successful(tmp_path) -> None:  # noqa: ANN001
    from app.core.artifacts import LocalArtifactProcessor

    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    processor = LocalArtifactProcessor(chat_id="chat_partial_upsert", api_prefix="/api/v1")
    event: dict[str, object] = {
        "type": "artifacts_ready",
        "data": [
            {"filename": "a.txt", "path": "a.txt", "type": "text"},
            {"filename": "b.txt", "path": "b.txt", "type": "text"},
        ],
        "read_content": AsyncMock(),
        "message_id": "msg_partial_upsert",
    }

    file_ids = iter(["file-a", "file-b"])

    def _next_file(**kwargs: object) -> MagicMock:
        mock_file = MagicMock()
        mock_file.id = next(file_ids)
        return mock_file

    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    async def _upsert_side_effect(db: object, *, file_id: str, **kwargs: object) -> str:
        if file_id == "file-b":
            raise RuntimeError("upsert failed for b")
        return "version-a"

    with (
        patch(
            "myrm_agent_harness.toolkits.code_execution.executors.base.get_executor",
            return_value=mock_executor,
        ),
        patch(
            "app.core.storage.service.FilesService.save_file_reference",
            new_callable=AsyncMock,
            side_effect=_next_file,
        ),
        patch(
            "app.core.artifacts.listener.upsert_processor_artifact",
            new_callable=AsyncMock,
            side_effect=_upsert_side_effect,
        ),
    ):
        result = await processor.process_artifacts_ready(event)

    assert result is not None
    data = result["data"]
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["filename"] == "a.txt"
    assert data[0]["id"] == "file-a"
