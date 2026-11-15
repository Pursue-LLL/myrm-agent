"""Reference image input: routing to the edit endpoint, the extra-reference warning and the explicit refusal."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.llms.image.generator import (
    ImageGenerationConfig,
    ImageGenerationError,
    ImageGenerator,
)
from myrm_agent_harness.toolkits.llms.image.models import ImageResult
from myrm_agent_harness.toolkits.llms.transport.images import GeneratedImage

_EDITABLE = "gpt-image-2.6-sunburst"
_GENERATE = "myrm_agent_harness.toolkits.llms.image.generator.agenerate_images"
_EDIT = "myrm_agent_harness.toolkits.llms.image.generator.aedit_images"


def _edited(model: str = _EDITABLE) -> ImageResult:
    return ImageResult(url="https://example.com/edited.png", b64_json=None, revised_prompt=None, model=model)


class TestGenerateWithReferences:
    @pytest.mark.asyncio()
    async def test_the_first_reference_is_routed_to_edit(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model=_EDITABLE, max_retries=0))

        with patch.object(gen, "edit", new_callable=AsyncMock, return_value=_edited()) as mock_edit:
            result = await gen.generate("edit the image", size="1536x1024", reference_images=[b"ref-image-bytes"])

        assert result.url == "https://example.com/edited.png"
        mock_edit.assert_called_once_with(
            b"ref-image-bytes",
            "edit the image",
            size="1536x1024",
            cancellation_event=None,
        )

    @pytest.mark.asyncio()
    async def test_extra_references_are_ignored_with_a_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model=_EDITABLE, max_retries=0))

        with (
            patch.object(gen, "edit", new_callable=AsyncMock, return_value=_edited()) as mock_edit,
            caplog.at_level(logging.WARNING, logger="myrm_agent_harness.toolkits.llms.image.generator"),
        ):
            await gen.generate("test", reference_images=[b"ref1", b"ref2", b"ref3"])

        assert "Only 1 reference image supported" in caplog.text
        assert mock_edit.call_args.args[0] == b"ref1"

    @pytest.mark.asyncio()
    async def test_a_model_that_accepts_no_input_images_fails_instead_of_dropping_them(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="flux/schnell", max_retries=0))

        with (
            patch(_GENERATE, new_callable=AsyncMock) as mock_generate,
            patch(_EDIT, new_callable=AsyncMock) as mock_edit,
            pytest.raises(ImageGenerationError, match=r"does not accept input images.*gpt-image-2"),
        ):
            await gen.generate("test", reference_images=[b"ref"])

        mock_generate.assert_not_awaited()
        mock_edit.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_an_unprofiled_model_gets_the_reference_and_the_provider_decides(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="custom/unknown-model", max_retries=0))

        with patch(_EDIT, new_callable=AsyncMock, return_value=[GeneratedImage(url="https://x/e.png")]) as mock_edit:
            await gen.generate("test", reference_images=[b"ref"])

        mock_edit.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_without_references_the_text_endpoint_is_used(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model=_EDITABLE, max_retries=0))

        with (
            patch(_GENERATE, new_callable=AsyncMock, return_value=[GeneratedImage(url="https://x/g.png")]) as mock_gen,
            patch(_EDIT, new_callable=AsyncMock) as mock_edit,
        ):
            await gen.generate("test")

        mock_gen.assert_awaited_once()
        mock_edit.assert_not_awaited()
