"""Image generation and editing with failover, retry and cancellation.

[INPUT]
- transport.images::{agenerate_images, aedit_images, GeneratedImage} (POS: provider image requests)
- models::{ImageGenerationConfig, ImageResult, ...} (POS: configuration and result types)
- types::{get_profile, editable_model_names} (POS: model capability lookup)

[OUTPUT]
- ImageGenerator: Core image generation and editing with failover, smart retry,
  latency tracking, cancellation support, instance-level metrics, reference image
  input and fail-closed media persistence

[POS]
Core image generation and editing engine. Calls the transport's image endpoints
(GPT Image, Gemini Imagen, Stability AI, Together Flux, xAI, MiniMax,
any OpenAI-compatible gateway) through one interface. One call produces one image.
Supports multi-model failover, reference image input (bytes the caller already
resolved), media storage decoupling via callback, SecretStr API key
protection, error message truncation, instance-level call metrics, cancellation
via asyncio.Event, and persistence that runs once on the final result: a generation whose
image cannot be stored fails instead of returning an artifact nobody can reach.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

import httpx

from myrm_agent_harness.toolkits.llms.transport.images import GeneratedImage, aedit_images, agenerate_images
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError

from .models import (
    FailoverAttempt,
    ImageGenerationConfig,
    ImageGenerationError,
    ImageResult,
    MediaCallback,
    MediaMeta,
)
from .types import editable_model_names, get_profile

__all__ = [
    "FailoverAttempt",
    "ImageGenerationConfig",
    "ImageGenerationError",
    "ImageGenerator",
    "ImageResult",
    "MediaCallback",
]

logger = logging.getLogger(__name__)

# Bad credentials, a rejected request and an unknown model fail the same way on every attempt.
_NON_RETRYABLE_STATUS = frozenset({400, 401, 404})
# A gateway that is down, out of balance or too slow is worth bypassing for the user's own provider key.
_GATEWAY_FAILURE_STATUS = frozenset({402, 502, 503, 504})
_ERROR_MSG_MAX_LEN = 500


def _is_retryable(exc: Exception) -> bool:
    """Whether another attempt can succeed: not for a refused request or an unreachable provider table entry."""
    if isinstance(exc, UnsupportedProviderError):
        return False
    return getattr(exc, "status_code", None) not in _NON_RETRYABLE_STATUS


def _is_gateway_failure(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException) or getattr(exc, "status_code", None) in _GATEWAY_FAILURE_STATUS:
        return True
    message = str(exc).lower()
    return "insufficient" in message or "timeout" in message


def _safe_truncate(msg: str, max_len: int = _ERROR_MSG_MAX_LEN) -> str:
    """Truncate error message to prevent sensitive data leakage."""
    if len(msg) <= max_len:
        return msg
    return msg[:max_len] + "... [truncated]"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ImageGenerator:
    """Image generation and editing across providers.

    Features multi-model failover, smart retry, instance-level metrics,
    and cancellation support.
    """

    def __init__(self, config: ImageGenerationConfig) -> None:
        self._config = config
        self._call_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    # -- Metrics properties ------------------------------------------------

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def total_latency_ms(self) -> float:
        return self._total_latency_ms

    # -- Public API --------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        reference_images: Sequence[bytes] = (),
        cancellation_event: asyncio.Event | None = None,
    ) -> ImageResult:
        """Generate one image from a text prompt with failover.

        Args:
            prompt: Text description of the desired image.
            size: Image dimensions as WIDTHxHEIGHT (overrides the config default).
            quality: Provider quality value; not sent when ``None`` so the provider applies its own default.
            reference_images: Image bytes the result should follow (style transfer, continuing an earlier image).
                They go through the provider's edit endpoint and only the first one is used; a model that
                accepts no input images fails instead of generating without them.
            cancellation_event: Set this event to cancel generation.

        Returns:
            ImageResult with URL or base64 data, plus the stored reference when a media callback is configured.

        Raises:
            ImageGenerationError: If generation fails across all models, the model accepts no input images
                while references were given, or the image cannot be stored.
        """
        if reference_images:
            profile = get_profile(self._config.model)
            if profile is not None and profile.max_input_images == 0:
                raise ImageGenerationError(
                    f"Model {self._config.model} does not accept input images. "
                    f"Models that do: {', '.join(editable_model_names())}"
                )
            if len(reference_images) > 1:
                logger.warning(
                    "Only 1 reference image supported per generation, using first of %d",
                    len(reference_images),
                )
            return await self.edit(
                reference_images[0],
                prompt,
                size=size,
                cancellation_event=cancellation_event,
            )

        effective_size = size or self._config.default_size

        async def call(model: str, bypass_gateway: bool) -> list[GeneratedImage]:
            api_key, api_base = self._credentials(bypass_gateway)
            return await agenerate_images(
                model,
                prompt,
                size=effective_size,
                quality=quality,
                api_key=api_key,
                api_base=api_base,
                timeout=self._config.timeout_seconds,
            )

        return await self._failover(
            call_factory=call,
            operation="generate",
            size_label=effective_size,
            cancellation_event=cancellation_event,
        )

    def _credentials(self, bypass_gateway: bool) -> tuple[str | None, str | None]:
        """``(api_key, api_base)`` of the next call: the tool gateway, or the user's own provider endpoint."""
        gateway = self._config.gateway_config
        if not bypass_gateway and gateway and gateway.use_gateway and gateway.gateway_url:
            return gateway.auth_token, f"{gateway.gateway_url.rstrip('/')}/image_gen"
        api_key = self._config.api_key.get_secret_value() if self._config.api_key else None
        return api_key, self._config.base_url or None

    async def edit(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        size: str | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> ImageResult:
        """Edit an image based on a text prompt with failover.

        Args:
            image: Source image data.
            prompt: Text description of the desired edit.
            mask: Optional mask image (transparent areas indicate edit regions).
            size: Output image dimensions (overrides config default).
            cancellation_event: Set this event to cancel editing.

        Returns:
            ImageResult with URL or base64 data.

        Raises:
            ImageGenerationError: If editing fails across all models or the image cannot be stored.
        """
        effective_size = size or self._config.default_size

        async def call(model: str, bypass_gateway: bool) -> list[GeneratedImage]:
            api_key, api_base = self._credentials(bypass_gateway)
            return await aedit_images(
                model,
                image,
                prompt,
                mask=mask,
                size=effective_size,
                api_key=api_key,
                api_base=api_base,
                timeout=self._config.timeout_seconds,
            )

        return await self._failover(
            call_factory=call,
            operation="edit",
            size_label=effective_size,
            cancellation_event=cancellation_event,
        )

    # -- Failover engine ---------------------------------------------------

    async def _failover(
        self,
        *,
        call_factory: Callable[[str, bool], Awaitable[list[GeneratedImage]]],
        operation: str,
        size_label: str,
        cancellation_event: asyncio.Event | None,
    ) -> ImageResult:
        """Try primary model, then each fallback in order; store the winning image once."""
        models = [self._config.model, *self._config.fallback_models]
        attempts: list[FailoverAttempt] = []
        self._call_count += 1

        for idx, model in enumerate(models):
            try:
                result = await self._call_with_retry(
                    call_factory=call_factory,
                    model=model,
                    operation=operation,
                    size_label=size_label,
                    cancellation_event=cancellation_event,
                )
            except ImageGenerationError as e:
                attempts.append(
                    FailoverAttempt(
                        model=model,
                        error=_safe_truncate(str(e)),
                        latency_ms=e.latency_ms,
                    )
                )
                if idx < len(models) - 1:
                    logger.warning(
                        "Image %s model %s failed, falling back to %s",
                        operation,
                        model,
                        models[idx + 1],
                    )
                    continue

                self._error_count += 1
                all_errors = "; ".join(f"[{a.model}] {a.error}" for a in attempts)
                raise ImageGenerationError(
                    f"All {len(models)} models failed for image {operation}. "
                    f"Attempts: {_safe_truncate(all_errors, 1000)}",
                    latency_ms=sum(a.latency_ms for a in attempts),
                ) from e
            else:
                # Outside the try: a storage failure is not a model failure, so it never triggers a fallback model.
                self._total_latency_ms += result.latency_ms
                return await self._persist(replace(result, attempts=attempts))

        raise ImageGenerationError("No models configured")

    async def _call_with_retry(
        self,
        call_factory: Callable[[str, bool], Awaitable[list[GeneratedImage]]],
        *,
        model: str,
        operation: str,
        size_label: str,
        cancellation_event: asyncio.Event | None,
    ) -> ImageResult:
        """Execute one image request with smart retry and gateway fallback."""
        last_error: Exception | None = None
        t0 = time.monotonic()

        bypass_gateway = False
        attempt = 0

        while attempt <= self._config.max_retries:
            if cancellation_event and cancellation_event.is_set():
                raise ImageGenerationError(
                    f"Image {operation} cancelled by user",
                    latency_ms=(time.monotonic() - t0) * 1000,
                )

            try:
                images = await call_factory(model, bypass_gateway)
                elapsed_ms = (time.monotonic() - t0) * 1000
                data = images[0]

                logger.info(
                    "Image %s: model=%s size=%s elapsed=%.0fms",
                    operation,
                    model,
                    size_label,
                    elapsed_ms,
                )
                return ImageResult(
                    url=data.url,
                    b64_json=data.b64_json,
                    revised_prompt=data.revised_prompt,
                    model=model,
                    latency_ms=elapsed_ms,
                )

            except Exception as exc:
                last_error = exc

                # Gateway Flexible Fallback Logic
                if (
                    not bypass_gateway
                    and self._config.gateway_config
                    and self._config.gateway_config.use_gateway
                    and self._config.api_key  # Must have a local API key to fallback to
                    and _is_gateway_failure(exc)
                ):
                    logger.warning(
                        "Gateway image %s failed (%s), falling back to direct provider API (BYOK)",
                        operation,
                        _safe_truncate(str(exc)),
                    )
                    bypass_gateway = True
                    continue  # the same attempt again over the direct connection: bypassing costs no retry

                if not _is_retryable(exc) or attempt >= self._config.max_retries:
                    break
                delay = 2.0 * (attempt + 1)
                logger.warning(
                    "Image %s attempt %d/%d (model=%s) failed: %s. Retrying in %.1fs",
                    operation,
                    attempt + 1,
                    self._config.max_retries + 1,
                    model,
                    _safe_truncate(str(exc)),
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

        elapsed_ms = (time.monotonic() - t0) * 1000
        raise ImageGenerationError(
            _safe_truncate(
                f"Image {operation} failed ({type(last_error).__name__}): {last_error} "
                f"[model={model}, elapsed={elapsed_ms:.0f}ms]"
            ),
            latency_ms=elapsed_ms,
        ) from last_error

    # -- Media persistence -------------------------------------------------

    async def _persist(self, result: ImageResult) -> ImageResult:
        """Store the image through the media callback and attach its stable reference.

        Fail-closed: with a callback configured, an image that cannot be stored (no data, callback error, empty
        reference) is a failed generation. Without one the result is returned as the provider gave it.
        """
        callback = self._config.media_callback
        if callback is None:
            return result
        try:
            pair = await result.to_bytes_with_mime()
            if pair is None:
                raise ValueError("the provider returned no downloadable image data")
            image_bytes, mime_type = pair
            reference = await callback(
                image_bytes, mime_type, MediaMeta(prompt=result.revised_prompt, model=result.model)
            )
            if not reference:
                raise ValueError("the media callback returned an empty reference")
        except Exception as exc:
            self._error_count += 1
            raise ImageGenerationError(
                _safe_truncate(f"Failed to store the generated image: {exc}"),
                latency_ms=result.latency_ms,
            ) from exc
        return replace(result, persisted_ref=reference, mime_type=mime_type)
