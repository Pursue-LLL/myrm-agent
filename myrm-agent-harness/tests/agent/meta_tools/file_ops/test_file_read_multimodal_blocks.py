"""file_read multimodal results: vision and PDF blocks, media text parts, video blocks and the PDF structure outline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal import (
    append_media_text_parts,
    build_multimodal_result,
)

_DUMMY_CONFIG = RunnableConfig()


@pytest.mark.asyncio
async def test_build_multimodal_vision_and_pdf(tmp_path: Path) -> None:
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    mock_executor = MagicMock()
    mock_executor.workspace_path = str(tmp_path)

    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": "img block"}],
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_pdf_as_content_blocks",
            new_callable=AsyncMock,
            return_value="pdf text",
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_video_as_content_blocks",
            new_callable=AsyncMock,
            return_value="video text",
        ),
    ):
        blocks = await build_multimodal_result(
            image_paths=[str(img)],
            pdf_paths=[str(pdf)],
            document_paths=[],
            text_paths=["notes.txt"],
            vault_paths=[],
            executor=mock_executor,
            skills=None,
            reason="test",
            url_errors=[],
            supports_vision=True,
            video_paths=[str(tmp_path / "clip.mp4")],
            config=_DUMMY_CONFIG,
        )

    texts = [b["text"] for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    assert any("img block" in t for t in texts)
    assert any("pdf text" in t for t in texts)
    assert any("video text" in t for t in texts)


@pytest.mark.asyncio
async def test_append_media_vision_fallback_path() -> None:
    mock_executor = MagicMock()
    parts: list[str] = []
    with patch(
        "myrm_agent_harness.toolkits.llms.vision.fallback_engine.VisionFallbackEngine.describe_local_image",
        new_callable=AsyncMock,
        return_value="described",
    ):
        await append_media_text_parts(
            parts,
            image_paths=["z.png"],
            pdf_paths=[],
            document_paths=[],
            video_paths=[],
            executor=mock_executor,
            supports_vision=False,
            vision_fallback_model_cfg={"model": "gpt-4o-mini", "api_key": "k"},
            parse_mode=None,
        )
    assert "described" in parts[0]


@pytest.mark.asyncio
async def test_build_multimodal_pdf_list_blocks() -> None:
    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_pdf_as_content_blocks",
        new_callable=AsyncMock,
        return_value=[{"type": "text", "text": "pdf blocks"}],
    ):
        blocks = await build_multimodal_result(
            image_paths=[],
            pdf_paths=["a.pdf"],
            document_paths=[],
            text_paths=[],
            vault_paths=[],
            executor=MagicMock(),
            skills=None,
            reason=None,
            url_errors=[],
            supports_vision=True,
            config=_DUMMY_CONFIG,
        )
    assert any("pdf blocks" in b.get("text", "") for b in blocks if isinstance(b, dict))

    blocks = await build_multimodal_result(
        image_paths=[],
        pdf_paths=[],
        document_paths=[],
        text_paths=[],
        vault_paths=[],
        executor=MagicMock(),
        skills=None,
        reason=None,
        url_errors=[],
        supports_vision=False,
        config=_DUMMY_CONFIG,
    )
    assert blocks[0]["text"] == "No results."


@pytest.mark.asyncio
async def test_append_media_text_parts_with_executor(tmp_path: Path) -> None:
    mock_executor = MagicMock()
    parts: list[str] = []
    with (
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
            new_callable=AsyncMock,
            return_value="image text",
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_pdf_as_content_blocks",
            new_callable=AsyncMock,
            return_value="pdf text",
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_document_as_text",
            new_callable=AsyncMock,
            return_value="doc text",
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_video_as_content_blocks",
            new_callable=AsyncMock,
            return_value="video text",
        ),
    ):
        await append_media_text_parts(
            parts,
            image_paths=["a.png"],
            pdf_paths=["b.pdf"],
            document_paths=["c.docx"],
            video_paths=["d.mp4"],
            executor=mock_executor,
            supports_vision=True,
            vision_fallback_model_cfg=None,
            parse_mode=None,
        )
    assert parts == ["image text", "pdf text", "doc text", "video text"]


@pytest.mark.asyncio
async def test_build_multimodal_video_list_blocks() -> None:
    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_video_as_content_blocks",
        new_callable=AsyncMock,
        return_value=[{"type": "text", "text": "vid-list"}],
    ):
        blocks = await build_multimodal_result(
            image_paths=[],
            pdf_paths=[],
            document_paths=[],
            text_paths=[],
            vault_paths=[],
            executor=MagicMock(),
            skills=None,
            reason=None,
            url_errors=[],
            supports_vision=True,
            video_paths=["clip.mp4"],
            config=_DUMMY_CONFIG,
        )
    assert any("vid-list" in b.get("text", "") for b in blocks if isinstance(b, dict))


@pytest.mark.asyncio
async def test_append_media_vision_fallback_failure() -> None:
    mock_executor = MagicMock()
    parts: list[str] = []
    with patch(
        "myrm_agent_harness.toolkits.llms.vision.fallback_engine.VisionFallbackEngine.describe_local_image",
        new_callable=AsyncMock,
        side_effect=RuntimeError("api down"),
    ):
        await append_media_text_parts(
            parts,
            image_paths=["z.png"],
            pdf_paths=[],
            document_paths=[],
            video_paths=[],
            executor=mock_executor,
            supports_vision=False,
            vision_fallback_model_cfg={"model": "gpt-4o-mini", "api_key": "k"},
            parse_mode=None,
        )
    assert "Vision analysis unavailable" in parts[0]


@pytest.mark.asyncio
async def test_pdf_reader_structure_mode() -> None:
    """验证 parse_mode='structure' 时 PDF 读取走大纲提取契约"""
    from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import (
        read_pdf_as_content_blocks,
    )
    from myrm_agent_harness.toolkits.file_parsers.base import PDFHeading, PDFParseResult

    mock_executor = MagicMock()
    mock_executor.read_file_bytes = AsyncMock(return_value=b"%PDF-1.4 mock")

    mock_res = PDFParseResult(
        text="",
        tables=[],
        metadata={"page_count": 10},
        headings=[
            PDFHeading(level=1, title="Introduction", page_num=1),
            PDFHeading(level=2, title="System Architecture", page_num=3),
        ],
    )

    with patch("myrm_agent_harness.toolkits.file_parsers.pdf.pdf.PDFPlumberParser.parse_sync", return_value=mock_res):
        out = await read_pdf_as_content_blocks(
            "paper.pdf", mock_executor, supports_vision=False, parse_mode="structure"
        )
        assert isinstance(out, str)
        assert "[DOCUMENT STRUCTURE OUTLINE: paper.pdf (Total Pages: 10)]:" in out
        assert "- Page 1: Introduction" in out
        assert "  - Page 3: System Architecture" in out
