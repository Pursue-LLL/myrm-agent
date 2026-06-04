from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.kanban.task_runner import (
    KanbanTaskRunner,
    _classify_content_type,
    _ResolvedProfile,
)


@pytest.mark.asyncio
async def test_kanban_task_runner_uses_unattended_mode():
    """Test that KanbanTaskRunner sets unattended_mode=True when creating GeneralAgentParams."""

    task = KanbanTask(
        task_id="test-task-1",
        board_id="board-1",
        title="Test Kanban Task",
        description="This is a test task",
        agent_id="test-agent-1",
    )

    mock_store = AsyncMock()
    mock_store.get_board.return_value = None
    runner = KanbanTaskRunner(mock_store)

    mock_model_cfg = ModelConfig(model="test-model", api_key="test-key")

    with patch(
        "app.ai_agents.agents.AgentFactory.create_general_agent"
    ) as mock_create_agent, patch(
        "app.services.kanban.task_runner.build_task_context", new_callable=AsyncMock
    ) as mock_build_context, patch.object(
        runner, "_resolve_profile", new_callable=AsyncMock
    ) as mock_resolve_profile, patch(
        "app.core.channel_bridge.config_loader.load_user_configs", new_callable=AsyncMock
    ) as mock_load_user_configs, patch(
        "app.core.channel_bridge.model_resolver.resolve_model_config",
        return_value=mock_model_cfg,
    ), patch(
        "app.core.channel_bridge.model_resolver.enrich_model_context_window",
        return_value=mock_model_cfg,
    ), patch(
        "app.services.agent.swarm_fission_resume.stream_with_swarm_fission_resume",
        new_callable=AsyncMock,
    ) as mock_stream:

        mock_build_context.return_value = "test context"
        mock_resolve_profile.return_value = None

        mock_configs = MagicMock()
        mock_configs.retrieval_dict = {}
        mock_configs.providers_dict = {"providers": []}
        mock_configs.security_config_dict = {}
        mock_configs.search_cfg = {"searchService": "tavily"}
        mock_configs.search_is_user_configured = False
        mock_load_user_configs.return_value = mock_configs

        mock_agent = AsyncMock()
        mock_create_agent.return_value = mock_agent

        async def mock_stream_gen(*args, **kwargs):
            yield {"type": "message_end", "usage": {}}

        mock_stream.side_effect = mock_stream_gen

        await runner.run(task)

        mock_create_agent.assert_called_once()
        params = mock_create_agent.call_args[0][0]

        assert isinstance(params, GeneralAgentParams)
        assert (
            params.unattended_mode is True
        ), "Kanban tasks must run in unattended_mode to prevent blocking"


class TestResolvedProfile:
    def test_agent_type_field_exists(self):
        """Verify _ResolvedProfile includes agent_type to prevent AttributeError."""
        profile = _ResolvedProfile(
            agent_type="team",
            system_prompt=None,
            model=None,
            skill_ids=(),
            subagent_ids=("sub1", "sub2"),
            security_overrides=None,
            max_iterations=None,
            memory_policy=None,
            memory_decay_profile=None,
            engine_params=None,
            auto_restore_domains=(),
            enabled_builtin_tools=("web_search",),
        )
        assert profile.agent_type == "team"

    def test_agent_type_default_individual(self):
        """Verify from_resolved defaults agent_type to 'individual'."""
        mock_resolved = MagicMock(spec=[])
        profile = _ResolvedProfile.from_resolved(mock_resolved)
        assert profile.agent_type == "individual"

    def test_from_resolved_extracts_agent_type(self):
        """Verify from_resolved correctly extracts agent_type from source."""
        mock_resolved = MagicMock()
        mock_resolved.agent_type = "team"
        mock_resolved.system_prompt = "test prompt"
        mock_resolved.model = "gpt-4"
        mock_resolved.skill_ids = ("skill1",)
        mock_resolved.subagent_ids = ("sub1",)
        mock_resolved.security_overrides = None
        mock_resolved.max_iterations = 50
        mock_resolved.memory_policy = None
        mock_resolved.memory_decay_profile = "normal"
        mock_resolved.engine_params = None
        mock_resolved.auto_restore_domains = ()
        mock_resolved.enabled_builtin_tools = ("web_search",)

        profile = _ResolvedProfile.from_resolved(mock_resolved)
        assert profile.agent_type == "team"
        assert profile.system_prompt == "test prompt"
        assert profile.model == "gpt-4"


class TestClassifyContentType:
    @pytest.mark.parametrize(
        ("content_type", "filename", "expected"),
        [
            ("image/png", "screenshot.png", "image"),
            ("image/jpeg", "photo.jpg", "image"),
            ("application/octet-stream", "diagram.webp", "image"),
            ("application/pdf", "doc.pdf", "pdf"),
            ("application/octet-stream", "report.pdf", "pdf"),
            ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "report.docx", "document"),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_pdf_text", return_value="extracted pdf content"),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_document_text", return_value="document text here"),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["img1", "pdf1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch.object(runner, "_extract_pdf_text", return_value="pdf extracted"),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["gone"]),
            patch("app.core.storage.files_service", mock_fs),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["bad"]),
            patch("app.core.storage.files_service", mock_fs),
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

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert result == "ctx"
        assert isinstance(result, str)


def _minimal_pdf_bytes() -> bytes:
    """PDF with Helvetica + literal text (valid xref offsets for pdfplumber)."""
    return b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 24 Tf 100 700 Td (kanban pdf text) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000264 00000 n 
0000000360 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
433
%%EOF"""


class TestBuildMultimodalRealExtraction:
    """Integration tests using real parsers (no mocked extract methods)."""

    @pytest.mark.asyncio
    async def test_real_pdf_extraction_in_query(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")
        pdf_bytes = _minimal_pdf_bytes()

        mock_file = MagicMock()
        mock_file.content_type = "application/pdf"
        mock_file.filename = "report.pdf"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_file_content = AsyncMock(return_value=pdf_bytes)

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

        assert isinstance(result, str)
        assert "kanban pdf text" in result
        assert "report.pdf" in result
        assert "## Attachment:" in result

    @pytest.mark.asyncio
    async def test_real_docx_extraction_in_query(self, tmp_path: Path) -> None:
        from docx import Document

        docx_path = tmp_path / "spec.docx"
        doc = Document()
        doc.add_paragraph("kanban fixture paragraph")
        doc.save(str(docx_path))
        docx_bytes = docx_path.read_bytes()

        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock()
        mock_file.content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        mock_file.filename = "spec.docx"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_file_content = AsyncMock(return_value=docx_bytes)

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

        assert isinstance(result, str)
        assert "kanban fixture paragraph" in result
        assert "spec.docx" in result

    @pytest.mark.asyncio
    async def test_extract_enabled_empty_pdf_falls_back_to_reference(self) -> None:
        from tests.services.files.test_content_extraction import _MINIMAL_PDF

        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock(content_type="application/pdf", filename="empty.pdf")
        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_file_content = AsyncMock(return_value=_MINIMAL_PDF)

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

        assert isinstance(result, str)
        assert "[Attachment: empty.pdf]" in result
        assert "## Attachment:" not in result

    @pytest.mark.asyncio
    async def test_extract_disabled_pdf_reference_only(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock(content_type="application/pdf", filename="report.pdf")
        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_file_content = AsyncMock(return_value=_minimal_pdf_bytes())

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": False}

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

        assert isinstance(result, str)
        assert "[Attachment: report.pdf]" in result
        assert "## Attachment:" not in result
