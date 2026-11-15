"""Tests for ImageGenerationTools: edit, model listing and the result shape."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.toolkits.llms.image.image_engine import (
    ImageGenerationTools,
    _format_result,
)
from myrm_agent_harness.toolkits.llms.image.models import (
    FailoverAttempt,
    ImageGenerationConfig,
    ImageResult,
)
from myrm_agent_harness.toolkits.llms.image.types import BUILTIN_PROFILES
from myrm_agent_harness.toolkits.llms.transport.images import GeneratedImage

_MODEL = "gpt-image-2.6-sunburst"
_EDIT = "myrm_agent_harness.toolkits.llms.image.generator.aedit_images"


class TestEditImage:
    @pytest.mark.asyncio()
    async def test_a_model_without_edit_support_is_refused(self) -> None:
        tools = ImageGenerationTools(ImageGenerationConfig(model="flux/schnell"))

        result = json.loads(await tools.edit_image(b"png-bytes", "edit it"))

        assert "not support" in result["error"].lower()

    @pytest.mark.asyncio()
    async def test_edit_returns_the_generation_result_shape(self) -> None:
        tools = ImageGenerationTools(ImageGenerationConfig(model=_MODEL))

        with patch(_EDIT, new_callable=AsyncMock) as mock:
            mock.return_value = [GeneratedImage(url="https://example.com/img.png", revised_prompt="revised")]
            result = json.loads(await tools.edit_image(b"png-bytes", "edit it"))

        assert result["images"] == [{"url": "https://example.com/img.png", "mime_type": "image/png"}]
        assert result["model"] == _MODEL
        assert result["prompt"] == "revised"

    @pytest.mark.asyncio()
    async def test_a_failed_edit_is_reported_as_an_error(self) -> None:
        tools = ImageGenerationTools(ImageGenerationConfig(model=_MODEL, max_retries=0))

        with patch(_EDIT, new_callable=AsyncMock, side_effect=RuntimeError("API error")):
            result = json.loads(await tools.edit_image(b"png-bytes", "edit it"))

        assert "error" in result
        assert "images" not in result


class TestListModels:
    def test_every_catalog_entry_is_listed(self) -> None:
        config = ImageGenerationConfig(model=_MODEL, fallback_models=["gpt-image-2.6-flare"])
        tools = ImageGenerationTools(config)

        result = json.loads(tools.list_models())

        assert len(result["models"]) >= len(BUILTIN_PROFILES)
        assert result["active_model"] == _MODEL
        assert result["fallback_models"] == ["gpt-image-2.6-flare"]


class TestFormatResult:
    def test_url_result(self) -> None:
        result = ImageResult(
            url="https://example.com/img.png",
            b64_json=None,
            revised_prompt="revised",
            model=_MODEL,
            latency_ms=1500.0,
        )
        output = json.loads(_format_result(result, "original"))
        assert output["images"] == [{"url": "https://example.com/img.png", "mime_type": "image/png"}]
        assert output["model"] == _MODEL
        assert output["prompt"] == "revised"
        assert output["latency_ms"] == 1500

    def test_the_stored_reference_replaces_the_provider_url(self) -> None:
        result = ImageResult(
            url="https://temp.com/img.png",
            b64_json=None,
            revised_prompt=None,
            model=_MODEL,
            persisted_ref="media://abc123",
            mime_type="image/webp",
        )
        output = json.loads(_format_result(result, "original"))
        assert output["images"] == [{"url": "media://abc123", "mime_type": "image/webp"}]
        assert output["prompt"] == "original"

    def test_failover_attempts_included(self) -> None:
        result = ImageResult(
            url="https://x.com/img.png",
            b64_json=None,
            revised_prompt=None,
            model="gpt-image-2.6-flare",
            attempts=[FailoverAttempt(model=_MODEL, error="failed", latency_ms=100)],
        )
        output = json.loads(_format_result(result, "original"))
        assert output["failover_attempts"] == [{"model": _MODEL, "error": "failed"}]
