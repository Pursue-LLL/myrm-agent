"""Tests for ImageGenerator: failover, retry classification, gateway fallback, metrics, cancellation, persistence."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.llms.image.generator import (
    ImageGenerationConfig,
    ImageGenerationError,
    ImageGenerator,
    _is_retryable,
    _safe_truncate,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError
from myrm_agent_harness.toolkits.llms.transport.images import GeneratedImage
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError

_GENERATE = "myrm_agent_harness.toolkits.llms.image.generator.agenerate_images"
_EDIT = "myrm_agent_harness.toolkits.llms.image.generator.aedit_images"
_TO_BYTES = "myrm_agent_harness.toolkits.llms.image.models.ImageResult.to_bytes_with_mime"


def _image(**overrides: str | None) -> list[GeneratedImage]:
    fields: dict[str, str | None] = {"url": "https://example.com/img.png", "revised_prompt": "revised prompt"}
    fields.update(overrides)
    return [GeneratedImage(**fields)]


def _http_error(status: int) -> LLMHTTPError:
    request = httpx.Request("POST", "https://api.example.com/v1/images/generations")
    response = httpx.Response(status, json={"error": {"message": "nope"}}, request=request)
    return LLMHTTPError("openai", status, response.text, response)


class TestSafeTruncate:
    def test_short_message(self) -> None:
        assert _safe_truncate("hello") == "hello"

    def test_long_message(self) -> None:
        msg = "x" * 600
        result = _safe_truncate(msg, max_len=100)
        assert len(result) < 120
        assert result.endswith("... [truncated]")


class TestSecretStr:
    def test_api_key_is_secret(self) -> None:
        config = ImageGenerationConfig(api_key=SecretStr("sk-secret-key"))
        assert "sk-secret-key" not in repr(config)
        assert "sk-secret-key" not in str(config)

    def test_api_key_none(self) -> None:
        config = ImageGenerationConfig()
        assert config.api_key is None


class TestRetryClassification:
    @pytest.mark.parametrize("status", [400, 401, 404])
    def test_refused_requests_are_not_retried(self, status: int) -> None:
        assert not _is_retryable(_http_error(status))

    @pytest.mark.parametrize("status", [403, 408, 422, 429, 500, 502, 503])
    def test_transient_and_policy_statuses_are_retried(self, status: int) -> None:
        assert _is_retryable(_http_error(status))

    def test_connection_failure_is_retried(self) -> None:
        assert _is_retryable(httpx.ConnectError("refused"))

    def test_unreachable_provider_is_not_retried(self) -> None:
        assert not _is_retryable(UnsupportedProviderError("no endpoint"))

    @pytest.mark.asyncio()
    async def test_non_retryable_error_stops_after_one_call(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", max_retries=2))
        with (
            patch(_GENERATE, new_callable=AsyncMock, side_effect=_http_error(401)) as mock,
            pytest.raises(ImageGenerationError),
        ):
            await gen.generate("test")
        assert mock.await_count == 1

    @pytest.mark.asyncio()
    async def test_retryable_error_is_retried(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", max_retries=1))
        with (
            patch(_GENERATE, new_callable=AsyncMock, side_effect=[_http_error(500), _image()]) as mock,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await gen.generate("test")
        assert mock.await_count == 2
        assert result.url == "https://example.com/img.png"


class TestImageGeneratorMetrics:
    @pytest.mark.asyncio()
    async def test_metrics_increment_on_success(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3"))

        assert gen.call_count == 0
        assert gen.error_count == 0
        assert gen.total_latency_ms == 0.0

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image()):
            await gen.generate("test prompt")

        assert gen.call_count == 1
        assert gen.error_count == 0
        assert gen.total_latency_ms > 0

    @pytest.mark.asyncio()
    async def test_metrics_error_count(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", max_retries=0))

        with (
            patch(_GENERATE, new_callable=AsyncMock, side_effect=RuntimeError("API down")),
            pytest.raises(ImageGenerationError),
        ):
            await gen.generate("test prompt")

        assert gen.call_count == 1
        assert gen.error_count == 1


class TestRequestParameters:
    @pytest.mark.asyncio()
    async def test_config_defaults_and_overrides_reach_the_call(self) -> None:
        config = ImageGenerationConfig(
            model="dall-e-3",
            api_key=SecretStr("sk-test"),
            base_url="https://proxy.example.com/v1",
            default_size="1024x1024",
            default_quality="standard",
            timeout_seconds=45,
        )
        gen = ImageGenerator(config)

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image()) as mock:
            await gen.generate("a cat", size="1792x1024", style="vivid", n=2)

        args, kwargs = mock.await_args
        assert args == ("dall-e-3", "a cat")
        assert kwargs == {
            "size": "1792x1024",
            "quality": "standard",
            "style": "vivid",
            "n": 2,
            "api_key": "sk-test",
            "api_base": "https://proxy.example.com/v1",
            "timeout": 45,
        }


class TestFailover:
    @pytest.mark.asyncio()
    async def test_failover_to_second_model(self) -> None:
        config = ImageGenerationConfig(model="primary-model", fallback_models=["fallback-model"], max_retries=0)
        gen = ImageGenerator(config)

        async def generate(model: str, prompt: str, **kwargs: object) -> list[GeneratedImage]:
            if model == "primary-model":
                raise RuntimeError("Primary failed")
            return _image(url=f"https://img/{model}")

        with patch(_GENERATE, side_effect=generate):
            result = await gen.generate("test prompt")

        assert result.model == "fallback-model"
        assert result.url == "https://img/fallback-model"
        assert len(result.attempts) == 1
        assert result.attempts[0].model == "primary-model"

    @pytest.mark.asyncio()
    async def test_all_models_fail(self) -> None:
        config = ImageGenerationConfig(model="m1", fallback_models=["m2", "m3"], max_retries=0)
        gen = ImageGenerator(config)

        with (
            patch(_GENERATE, new_callable=AsyncMock, side_effect=RuntimeError("all fail")),
            pytest.raises(ImageGenerationError, match="All 3 models failed"),
        ):
            await gen.generate("test")

    @pytest.mark.asyncio()
    async def test_primary_success_no_failover(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="primary", fallback_models=["fallback"]))

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image()):
            result = await gen.generate("test")

        assert result.model == "primary"
        assert result.attempts == []


class TestGatewayFallback:
    @staticmethod
    def _config(**overrides: object) -> ImageGenerationConfig:
        gateway = ToolGatewayConfig(use_gateway=True, gateway_url="https://gw.example.com/", auth_token="gw-token")
        return ImageGenerationConfig(
            model="dall-e-3",
            api_key=SecretStr("sk-own"),
            gateway_config=gateway,
            max_retries=0,
            **overrides,
        )

    @pytest.mark.asyncio()
    async def test_gateway_is_used_first(self) -> None:
        gen = ImageGenerator(self._config())

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image()) as mock:
            await gen.generate("test")

        kwargs = mock.await_args.kwargs
        assert kwargs["api_key"] == "gw-token"
        assert kwargs["api_base"] == "https://gw.example.com/image_gen"

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("failure", [_http_error(502), _http_error(402), httpx.ReadTimeout("")])
    async def test_gateway_failure_falls_back_to_own_key(self, failure: Exception) -> None:
        gen = ImageGenerator(self._config())

        with patch(_GENERATE, new_callable=AsyncMock, side_effect=[failure, _image()]) as mock:
            result = await gen.generate("test")

        assert result.url == "https://example.com/img.png"
        assert mock.await_args_list[1].kwargs["api_key"] == "sk-own"
        assert mock.await_args_list[1].kwargs["api_base"] is None

    @pytest.mark.asyncio()
    async def test_non_gateway_failure_does_not_bypass(self) -> None:
        gen = ImageGenerator(self._config())

        with (
            patch(_GENERATE, new_callable=AsyncMock, side_effect=_http_error(400)) as mock,
            pytest.raises(ImageGenerationError),
        ):
            await gen.generate("test")

        assert mock.await_count == 1


class TestEditFailover:
    """Verify image bytes are preserved across failover retries."""

    @pytest.mark.asyncio()
    async def test_edit_failover_preserves_image_data(self) -> None:
        config = ImageGenerationConfig(model="primary", fallback_models=["fallback"], max_retries=0)
        gen = ImageGenerator(config)
        image_data = b"PNG-image-content-here"
        received: list[bytes] = []

        async def edit(model: str, image: bytes, prompt: str, **kwargs: object) -> list[GeneratedImage]:
            received.append(image)
            if model == "primary":
                raise RuntimeError("Primary edit failed")
            return _image()

        with patch(_EDIT, side_effect=edit):
            result = await gen.edit(image_data, "edit prompt")

        assert result.model == "fallback"
        assert received == [image_data, image_data]

    @pytest.mark.asyncio()
    async def test_edit_materialises_file_like_inputs(self) -> None:
        import io

        gen = ImageGenerator(ImageGenerationConfig(model="gpt-image-1", max_retries=0))

        with patch(_EDIT, new_callable=AsyncMock, return_value=_image()) as mock:
            await gen.edit(io.BytesIO(b"image"), "edit", mask=io.BytesIO(b"mask"), size="1024x1024", n=2)

        args, kwargs = mock.await_args
        assert args == ("gpt-image-1", b"image", "edit")
        assert kwargs["mask"] == b"mask"
        assert kwargs["n"] == 2


class TestCancellation:
    @pytest.mark.asyncio()
    async def test_cancellation_before_call(self) -> None:
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", max_retries=0))

        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(ImageGenerationError, match="cancelled"):
            await gen.generate("test", cancellation_event=cancel)


class TestMediaCallback:
    @pytest.mark.asyncio()
    async def test_callback_invoked_on_b64(self) -> None:
        callback = AsyncMock(return_value="https://storage/persisted.png")
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", media_callback=callback))
        b64_data = base64.b64encode(b"fake-image-bytes").decode()

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image(url=None, b64_json=b64_data)):
            result = await gen.generate("test")

        assert result.persisted_url == "https://storage/persisted.png"
        callback.assert_called_once()

    @pytest.mark.asyncio()
    async def test_callback_invoked_on_url_result(self) -> None:
        """URL results are downloaded then persisted via callback."""
        callback = AsyncMock(return_value="https://storage/persisted.png")
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", media_callback=callback))
        fake_image_bytes = b"downloaded-image-content"

        with (
            patch(_GENERATE, new_callable=AsyncMock, return_value=_image(url="https://api/img.png")),
            patch(_TO_BYTES, new_callable=AsyncMock, return_value=(fake_image_bytes, "image/png")),
        ):
            result = await gen.generate("test")

        assert result.persisted_url == "https://storage/persisted.png"
        assert result.mime_type == "image/png"
        callback.assert_called_once()
        assert callback.call_args[0][0] == fake_image_bytes
        assert callback.call_args[0][1] == "image/png"

    @pytest.mark.asyncio()
    async def test_no_callback_without_config(self) -> None:
        """No persistence when media_callback is not configured."""
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3"))

        with patch(_GENERATE, new_callable=AsyncMock, return_value=_image(url="https://api/img.png")):
            result = await gen.generate("test")

        assert result.persisted_url is None

    @pytest.mark.asyncio()
    async def test_callback_failure_does_not_break_generation(self) -> None:
        """Persistence failure is swallowed — generation result still returned."""
        callback = AsyncMock(side_effect=OSError("storage unavailable"))
        gen = ImageGenerator(ImageGenerationConfig(model="dall-e-3", media_callback=callback))

        with (
            patch(_GENERATE, new_callable=AsyncMock, return_value=_image(url="https://api/img.png")),
            patch(_TO_BYTES, new_callable=AsyncMock, return_value=(b"image-bytes", "image/png")),
        ):
            result = await gen.generate("test")

        assert result.url == "https://api/img.png"
        assert result.persisted_url is None
        assert gen.call_count == 1
        assert gen.error_count == 0
