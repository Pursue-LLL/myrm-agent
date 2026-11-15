"""Video generation orchestrator.

Handles multi-provider failover, content normalization, and task lifecycle.

[INPUT]
- _overrides::sanitize_overrides (POS: Pure function that fits request params to a provider's declared capabilities)

[OUTPUT]
- VideoGenerator: Video generation with failover and override sanitization.

[POS]
Video generation orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace

from ._helpers import is_retryable, safe_truncate, validate_video_content
from ._overrides import sanitize_overrides
from .models import (
    FailoverAttempt,
    MediaMeta,
    ModerationBlockedError,
    VideoGenerationConfig,
    VideoGenerationError,
    VideoResult,
)
from .providers.base import ProviderOutput, ProviderRegistry

logger = logging.getLogger(__name__)


class VideoGenerator:
    """Video generation with failover and override sanitization.

    Lifecycle:
    1. Resolve provider/model from config chain
    2. Sanitize request params against provider capabilities
    3. Call provider.generate() with retry
    4. On failure, try next fallback config
    5. Persist the winning result via media_callback (fail-closed: a video that cannot be stored fails the call)
    """

    __slots__ = ("_call_count", "_config", "_error_count", "_registry", "_total_latency_ms")

    def __init__(self, config: VideoGenerationConfig, registry: ProviderRegistry) -> None:
        self._config = config
        self._registry = registry
        self._call_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def total_latency_ms(self) -> float:
        return self._total_latency_ms

    async def generate(
        self,
        prompt: str,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        duration_seconds: int | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        enable_audio: bool | None = None,
        reference_images: list[bytes] | None = None,
        reference_videos: list[bytes] | None = None,
        extra_params: dict[str, object] | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> VideoResult:
        """Generate video with ordered failover across provider configs.

        Priority chain: explicit args → primary config → fallback configs.
        Unsupported overrides are silently dropped and reported in the result.
        Per-provider timeout is enforced via config.timeout_seconds.
        """
        configs = self._build_config_chain(provider_id, model)
        attempts: list[FailoverAttempt] = []
        self._call_count += 1

        for idx, cfg in enumerate(configs):
            provider = self._registry.get(cfg.provider)
            if not provider:
                attempts.append(
                    FailoverAttempt(
                        provider=cfg.provider,
                        model=cfg.model,
                        error=f"Provider '{cfg.provider}' not registered",
                    )
                )
                continue

            effective_model = cfg.model or provider.default_model
            t_start = time.monotonic()
            try:
                coro = self._call_with_retry(
                    prompt=prompt,
                    config=cfg,
                    provider_id=cfg.provider,
                    model_id=effective_model,
                    duration_seconds=duration_seconds,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    enable_audio=enable_audio,
                    reference_images=reference_images,
                    reference_videos=reference_videos,
                    extra_params=extra_params,
                    cancellation_event=cancellation_event,
                )
                result = await asyncio.wait_for(coro, timeout=cfg.timeout_seconds)

            except TimeoutError:
                elapsed_ms = (time.monotonic() - t_start) * 1000
                timeout_msg = f"Provider '{cfg.provider}/{effective_model}' timed out after {cfg.timeout_seconds}s"
                logger.warning(timeout_msg)
                attempts.append(
                    FailoverAttempt(
                        provider=cfg.provider,
                        model=effective_model,
                        error=timeout_msg,
                        latency_ms=elapsed_ms,
                    )
                )
                if idx < len(configs) - 1:
                    continue
                self._error_count += 1
                all_errors = "; ".join(f"[{a.provider}/{a.model}] {a.error}" for a in attempts)
                raise VideoGenerationError(
                    f"All {len(configs)} provider(s) failed. Attempts: {safe_truncate(all_errors, 1000)}",
                    latency_ms=sum(a.latency_ms for a in attempts),
                ) from None

            except ModerationBlockedError:
                self._error_count += 1
                logger.warning(
                    "Video generation blocked by content moderation on %s/%s; aborting failover.",
                    cfg.provider,
                    effective_model,
                )
                raise

            except VideoGenerationError as e:
                attempts.append(
                    FailoverAttempt(
                        provider=cfg.provider,
                        model=effective_model,
                        error=safe_truncate(str(e)),
                        latency_ms=e.latency_ms,
                    )
                )
                if idx < len(configs) - 1:
                    next_cfg = configs[idx + 1]
                    logger.warning(
                        "Video generation %s/%s failed, falling back to %s/%s",
                        cfg.provider,
                        effective_model,
                        next_cfg.provider,
                        next_cfg.model,
                    )
                    continue

                self._error_count += 1
                all_errors = "; ".join(f"[{a.provider}/{a.model}] {a.error}" for a in attempts)
                raise VideoGenerationError(
                    f"All {len(configs)} provider(s) failed. Attempts: {safe_truncate(all_errors, 1000)}",
                    latency_ms=sum(a.latency_ms for a in attempts),
                ) from e

            else:
                # Outside the try: a storage failure is not a provider failure, so it never triggers a fallback.
                self._total_latency_ms += result.latency_ms
                return await self._persist(replace(result, attempts=attempts), prompt)

        self._error_count += 1
        raise VideoGenerationError("No video providers configured or registered")

    def _build_config_chain(
        self,
        provider_id: str | None,
        model: str | None,
    ) -> list[VideoGenerationConfig]:
        """Build ordered list of configs to try: explicit → primary → fallbacks."""
        if provider_id or model:
            override = self._config.model_copy(
                update={k: v for k, v in {"provider": provider_id, "model": model}.items() if v is not None}
            )
            return [override, *self._config.fallback_configs]
        return [self._config, *self._config.fallback_configs]

    async def _call_with_retry(
        self,
        *,
        prompt: str,
        config: VideoGenerationConfig,
        provider_id: str,
        model_id: str,
        duration_seconds: int | None,
        aspect_ratio: str | None,
        resolution: str | None,
        enable_audio: bool | None,
        reference_images: list[bytes] | None,
        reference_videos: list[bytes] | None,
        extra_params: dict[str, object] | None,
        cancellation_event: asyncio.Event | None,
    ) -> VideoResult:
        provider = self._registry.get(provider_id)
        if not provider:
            raise VideoGenerationError(f"Provider '{provider_id}' not found")

        sanitized, ignored, normalizations = sanitize_overrides(
            provider.capabilities,
            provider_id=provider_id,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_audio=enable_audio,
            reference_images=reference_images,
            reference_videos=reference_videos,
        )

        last_error: Exception | None = None
        t0 = time.monotonic()

        for attempt in range(config.max_retries + 1):
            if cancellation_event and cancellation_event.is_set():
                raise VideoGenerationError(
                    "Video generation cancelled by user",
                    latency_ms=(time.monotonic() - t0) * 1000,
                )

            try:
                output: ProviderOutput = await provider.generate(
                    prompt,
                    config,
                    model=model_id,
                    duration_seconds=sanitized.duration_seconds,
                    aspect_ratio=sanitized.aspect_ratio,
                    resolution=sanitized.resolution,
                    enable_audio=sanitized.enable_audio,
                    reference_images=sanitized.reference_images,
                    reference_videos=sanitized.reference_videos,
                    extra_params=extra_params,
                )

                for video in output.assets:
                    validate_video_content(video.data, provider_id, model_id)

                elapsed_ms = (time.monotonic() - t0) * 1000

                logger.info(
                    "Video generated: provider=%s model=%s elapsed=%.0fms",
                    provider_id,
                    model_id,
                    elapsed_ms,
                )
                return VideoResult(
                    videos=output.assets,
                    provider=provider_id,
                    model=model_id,
                    latency_ms=elapsed_ms,
                    ignored_overrides=ignored,
                    normalizations=normalizations,
                    revised_prompt=output.revised_prompt,
                )

            except Exception as exc:
                msg_lower = str(exc).lower()
                is_422 = getattr(exc, "status_code", None) == 422 or getattr(exc, "code", None) == 422
                has_safety_keywords = (
                    "content_filter" in msg_lower
                    or "moderation" in msg_lower
                    or "sensitive" in msg_lower
                    or "safety" in msg_lower
                    or "policy" in msg_lower
                    or "violation" in msg_lower
                    or "nsfw" in msg_lower
                    or "copyright" in msg_lower
                )
                is_mod_blocked = (
                    isinstance(exc, ModerationBlockedError)
                    or (is_422 and has_safety_keywords)
                    or "content_filter" in msg_lower
                    or "moderation" in msg_lower
                    or "sensitive content" in msg_lower
                    or "safety policy" in msg_lower
                    or "nsfw" in msg_lower
                )
                if is_mod_blocked:
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    reason = "Content safety or moderation policy violation"
                    if "nsfw" in msg_lower:
                        reason = "Content flagged for NSFW safety policy violation"
                    elif "copyright" in msg_lower:
                        reason = "Content flagged for potential copyright or IP violation"
                    raise ModerationBlockedError(
                        safe_truncate(f"Video generation rejected by safety filter: {exc}"),
                        violation_reason=reason,
                        latency_ms=elapsed_ms,
                    ) from exc

                last_error = exc
                if not is_retryable(exc) or attempt >= config.max_retries:
                    break
                delay = 2.0 * (attempt + 1)
                logger.warning(
                    "Video gen attempt %d/%d (%s/%s) failed: %s. Retrying in %.1fs",
                    attempt + 1,
                    config.max_retries + 1,
                    provider_id,
                    model_id,
                    safe_truncate(str(exc)),
                    delay,
                )
                await asyncio.sleep(delay)

        elapsed_ms = (time.monotonic() - t0) * 1000
        raise VideoGenerationError(
            safe_truncate(
                f"Video generation failed ({type(last_error).__name__}): {last_error} "
                f"[provider={provider_id}, model={model_id}, elapsed={elapsed_ms:.0f}ms]"
            ),
            latency_ms=elapsed_ms,
        ) from last_error

    async def _persist(self, result: VideoResult, prompt: str) -> VideoResult:
        """Store every video through the primary config's media callback and attach the stable references.

        Fail-closed: with a callback configured, a video that cannot be stored (callback error, empty reference) is a
        failed generation. The primary callback stores videos made by any fallback provider too.
        """
        callback = self._config.media_callback
        if callback is None:
            return result
        references: list[str] = []
        try:
            for video in result.videos:
                meta = MediaMeta(prompt=prompt, model=result.model, provider=result.provider)
                reference = await callback(video.data, video.mime_type, meta)
                if not reference:
                    raise ValueError("the media callback returned an empty reference")
                references.append(reference)
        except Exception as exc:
            self._error_count += 1
            raise VideoGenerationError(
                safe_truncate(f"Failed to store the generated video: {exc}"),
                latency_ms=result.latency_ms,
            ) from exc
        return replace(result, persisted_refs=references)
