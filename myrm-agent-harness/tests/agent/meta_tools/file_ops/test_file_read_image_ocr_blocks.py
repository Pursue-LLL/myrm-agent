"""file_read image results: block lists, the string result without a vision route, and the OCR tier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal import (
    build_multimodal_result,
)

_DUMMY_CONFIG = RunnableConfig()


@pytest.mark.asyncio
async def test_build_multimodal_image_list_blocks() -> None:
    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
        new_callable=AsyncMock,
        return_value=[{"type": "text", "text": "img-list"}],
    ):
        blocks = await build_multimodal_result(
            image_paths=["a.png"],
            pdf_paths=[],
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
    assert any("img-list" in b.get("text", "") for b in blocks if isinstance(b, dict))


@pytest.mark.asyncio
async def test_build_multimodal_image_no_vision_string_result() -> None:
    with patch(
        "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
        new_callable=AsyncMock,
        return_value="plain image text",
    ):
        blocks = await build_multimodal_result(
            image_paths=["a.png"],
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
    assert blocks[0]["text"] == "plain image text"


@pytest.mark.asyncio
async def test_build_multimodal_image_uses_ocr_tier_when_no_vision_route_exists() -> None:
    """A text-only model with no vision chain still reads image text via the OCR tier.

    Regression: the OCR tier existed but nothing invoked it, so such a model got only a
    metadata line ("model does not support vision") for every image.
    """
    with patch(
        "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
        new_callable=AsyncMock,
    ) as mock_ocr:
        from myrm_agent_harness.toolkits.llms.vision.types import VisionBackendKind, VisionResult

        mock_ocr.return_value = VisionResult(
            text="INVOICE TOTAL 12345.67",
            backend_kind=VisionBackendKind.OCR,
        )
        blocks = await build_multimodal_result(
            image_paths=["a.png"],
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

    mock_ocr.assert_awaited_once()
    assert "INVOICE TOTAL 12345.67" in blocks[0]["text"]


@pytest.mark.asyncio
async def test_build_multimodal_image_empty_ocr_falls_back_to_metadata() -> None:
    """When the OCR tier finds no text, the caller must keep its metadata response."""
    from myrm_agent_harness.toolkits.llms.vision.types import VisionBackendKind, VisionResult

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
            new_callable=AsyncMock,
            return_value=VisionResult(
                text="[OCR found no readable text]",
                backend_kind=VisionBackendKind.OCR,
            ),
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
            new_callable=AsyncMock,
            return_value="metadata only",
        ),
    ):
        blocks = await build_multimodal_result(
            image_paths=["a.png"],
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

    assert blocks[0]["text"] == "metadata only"


@pytest.mark.asyncio
async def test_build_multimodal_image_propagates_block_list_from_plain_reader() -> None:
    """When the OCR tier finds nothing, a block list from the plain reader must be extended, not dropped.

    ``read_image_as_content_blocks`` may return blocks; appending it as one item would bury
    the content inside a text block instead of surfacing it.
    """
    from myrm_agent_harness.toolkits.llms.vision.types import VisionBackendKind, VisionResult

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
            new_callable=AsyncMock,
            return_value=VisionResult(
                text="[OCR found no readable text]",
                backend_kind=VisionBackendKind.OCR,
            ),
        ),
        patch(
            "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal.read_image_as_content_blocks",
            new_callable=AsyncMock,
            return_value=[{"type": "text", "text": "block-a"}, {"type": "text", "text": "block-b"}],
        ),
    ):
        blocks = await build_multimodal_result(
            image_paths=["a.png"],
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

    assert [block["text"] for block in blocks] == ["block-a", "block-b"]


class TestReadImageViaOcr:
    """The last-resort OCR tier: text, no text, and unavailable."""

    @pytest.mark.asyncio
    async def test_returns_text_when_ocr_reads_the_image(self) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal import (
            _read_image_via_ocr,
        )
        from myrm_agent_harness.toolkits.llms.vision.types import VisionBackendKind, VisionResult

        with patch(
            "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
            new_callable=AsyncMock,
            return_value=VisionResult(text="INVOICE 42", backend_kind=VisionBackendKind.OCR),
        ):
            result = await _read_image_via_ocr("a.png", AsyncMock())

        assert result is not None
        assert "INVOICE 42" in result

    @pytest.mark.asyncio
    async def test_returns_none_when_ocr_finds_no_text(self) -> None:
        from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal import (
            _read_image_via_ocr,
        )
        from myrm_agent_harness.toolkits.llms.vision.types import VisionBackendKind, VisionResult

        with patch(
            "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
            new_callable=AsyncMock,
            return_value=VisionResult(text="[OCR found no readable text]", backend_kind=VisionBackendKind.OCR),
        ):
            result = await _read_image_via_ocr("a.png", AsyncMock())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_the_ocr_extra_is_absent(self) -> None:
        """A missing extra must not be reported as "the image had no text"."""
        from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.multimodal import (
            _read_image_via_ocr,
        )

        with patch(
            "myrm_agent_harness.toolkits.llms.vision.ocr_tier.OcrTierEngine.describe_local_image",
            new_callable=AsyncMock,
            side_effect=ImportError("rapidocr is required"),
        ):
            result = await _read_image_via_ocr("a.png", AsyncMock())

        assert result is None
