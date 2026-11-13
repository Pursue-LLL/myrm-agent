"""How a kanban run reads a task's attachments and workspace into the prompt it hands the agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.kanban.task_runner import KanbanTaskRunner, _classify_content_type


class TestClassifyContentType:
    @pytest.mark.parametrize(
        ("content_type", "filename", "expected"),
        [
            ("image/png", "screenshot.png", "image"),
            ("image/jpeg", "photo.jpg", "image"),
            ("application/octet-stream", "diagram.webp", "image"),
            ("application/pdf", "doc.pdf", "pdf"),
            ("application/octet-stream", "report.pdf", "pdf"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "report.docx",
                "document",
            ),
            ("application/octet-stream", "slides.pptx", "document"),
            ("text/plain", "notes.txt", "other"),
            ("application/json", "config.json", "other"),
        ],
    )
    def test_classify(self, content_type: str, filename: str, expected: str) -> None:
        assert _classify_content_type(content_type, filename) == expected


class TestBuildMultimodalQuery:
    @pytest.mark.asyncio
    async def test_no_attachments_returns_text(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        with patch.object(runner, "_load_attachment_ids", return_value=[]):
            result = await runner._build_multimodal_query(task, "context text")

        assert result == "context text"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_image_attachments_return_multimodal(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock()
        mock_file.content_type = "image/png"
        mock_file.filename = "screenshot.png"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, list)
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_pdf_attachment_appends_text(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock()
        mock_file.content_type = "application/pdf"
        mock_file.filename = "report.pdf"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_pdf_text", return_value="extracted pdf content"),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "extracted pdf content" in result
        assert "report.pdf" in result

    @pytest.mark.asyncio
    async def test_document_attachment_appends_text(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock()
        mock_file.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mock_file.filename = "spec.docx"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_document_text", return_value="document text here"),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "document text here" in result
        assert "spec.docx" in result

    @pytest.mark.asyncio
    async def test_mixed_attachments_image_plus_pdf(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        img_file = MagicMock(content_type="image/png", filename="diagram.png")
        pdf_file = MagicMock(content_type="application/pdf", filename="notes.pdf")

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(side_effect=lambda fid: img_file if fid == "img1" else pdf_file)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["img1", "pdf1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_pdf_text", return_value="pdf extracted"),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "base")

        assert isinstance(result, list)
        assert result[0]["type"] == "text"
        assert "pdf extracted" in result[0]["text"]
        assert "notes.pdf" in result[0]["text"]
        assert result[1]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_missing_file_skipped(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=None)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["gone"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert result == "ctx"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_file_processing_exception_skipped(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(side_effect=RuntimeError("storage down"))

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["bad"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "fallback")

        assert result == "fallback"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_other_file_type_skipped(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock(content_type="text/plain", filename="notes.txt")
        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert result == "ctx"
        assert isinstance(result, str)


class TestAugmentContext:
    """Direct unit tests for KanbanTaskRunner._augment_context."""

    def _task(self, metadata: dict | None) -> KanbanTask:
        return KanbanTask(
            task_id="ctx-task",
            board_id="board-1",
            title="Context task",
            description="d",
            metadata=metadata or {},
        )

    def test_augment_context_appends_workspace_root(self) -> None:
        task = self._task({})
        out = KanbanTaskRunner._augment_context(task, "base context", "/tmp/ws")
        assert "## Execution environment" in out
        assert "Workspace root: /tmp/ws" in out
        assert out.startswith("base context")

    def test_augment_context_appends_annotations(self) -> None:
        task = self._task({"context_annotations": ["Pattern A", "Pattern B"]})
        out = KanbanTaskRunner._augment_context(task, "base", None)
        assert "Pattern A" in out
        assert "Pattern B" in out

    def test_augment_context_keeps_context_when_nothing_to_add(self) -> None:
        task = self._task({})
        out = KanbanTaskRunner._augment_context(task, "base", None)
        assert out == "base"

    def test_augment_context_ignores_non_list_annotations(self) -> None:
        task = self._task({"context_annotations": "not-a-list"})
        out = KanbanTaskRunner._augment_context(task, "base", "/tmp/ws")
        assert "not-a-list" not in out
        assert "Workspace root: /tmp/ws" in out
