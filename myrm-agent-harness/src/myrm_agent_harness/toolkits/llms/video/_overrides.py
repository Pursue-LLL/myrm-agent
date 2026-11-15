"""Request parameter sanitization against a video provider's declared capabilities.

[INPUT]
- toolkits.llms._media_shared.normalization::NormalizationResult, normalize_params (POS: Snaps a requested aspect ratio, size and duration to the closest values a provider mode declares as supported and reports each adjustment as a NormalizationRecord.)
- toolkits.llms._media_shared.types::ModeCapabilities, NormalizationRecord (POS: Defines the contract between provider capability declarations and the normalization engine.)
- models::OverrideIgnored, ProviderCapabilities (POS: Pure data types of the video module)

[OUTPUT]
- SanitizedOverrides: the request params a provider can honour (``None`` = not requested or not supported)
- sanitize_overrides(): the honoured params, the overrides it ignores and the normalizations applied

[POS]
Pure function (no state, no I/O) that generator.py calls once per provider before its attempt loop; the result is reused by every retry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.llms._media_shared.normalization import (
    NormalizationResult,
    normalize_params,
)
from myrm_agent_harness.toolkits.llms._media_shared.types import (
    ModeCapabilities,
    NormalizationRecord,
)

from .models import OverrideIgnored, ProviderCapabilities

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SanitizedOverrides:
    """Request params a provider can honour; ``None`` means not requested or not supported by the provider."""

    duration_seconds: int | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    enable_audio: bool | None = None
    reference_images: list[bytes] | None = None
    reference_videos: list[bytes] | None = None


def _detect_mode_capabilities(
    caps: ProviderCapabilities,
    reference_images: list[bytes] | None,
    reference_videos: list[bytes] | None,
) -> ModeCapabilities | None:
    """Auto-detect generation mode from inputs and return matching capabilities.

    Priority: V2V > I2V > T2V, decided by which reference inputs are present.
    Returns None if the provider has no mode_capabilities declared.
    """
    mc = caps.mode_capabilities
    if mc is None:
        return None

    if reference_videos and mc.video_to_video:
        return mc.video_to_video
    if reference_images and mc.image_to_video:
        return mc.image_to_video
    if mc.generate:
        return mc.generate
    return None


def sanitize_overrides(
    caps: ProviderCapabilities,
    *,
    provider_id: str,
    duration_seconds: int | None,
    aspect_ratio: str | None,
    resolution: str | None,
    enable_audio: bool | None,
    reference_images: list[bytes] | None,
    reference_videos: list[bytes] | None,
) -> tuple[SanitizedOverrides, list[OverrideIgnored], list[NormalizationRecord]]:
    """Sanitize and normalize request params against provider capabilities.

    Uses the normalization engine when mode_capabilities are declared,
    falling back to simple accept/ignore logic for providers without it.
    Returns (sanitized_params, ignored_overrides, normalization_records).
    """
    result = SanitizedOverrides()
    ignored: list[OverrideIgnored] = []
    normalizations: list[NormalizationRecord] = []

    mode_caps = _detect_mode_capabilities(
        caps,
        reference_images,
        reference_videos,
    )

    if mode_caps is not None:
        norm_result: NormalizationResult = normalize_params(
            caps=mode_caps,
            requested_ratio=aspect_ratio,
            requested_size=resolution,
            requested_duration=duration_seconds,
        )
        if norm_result.aspect_ratio:
            result.aspect_ratio = norm_result.aspect_ratio
        if norm_result.size:
            result.resolution = f"{norm_result.size.width}x{norm_result.size.height}"
        elif resolution is not None and caps.supports_resolution:
            result.resolution = resolution
        if norm_result.duration_seconds is not None:
            result.duration_seconds = norm_result.duration_seconds
        elif duration_seconds is not None:
            result.duration_seconds = duration_seconds
        if norm_result.records:
            normalizations.extend(norm_result.records)
    else:
        if duration_seconds is not None:
            result.duration_seconds = duration_seconds
        if aspect_ratio is not None:
            if caps.supports_aspect_ratio:
                result.aspect_ratio = aspect_ratio
            else:
                ignored.append(OverrideIgnored(key="aspect_ratio", value=aspect_ratio))
        if resolution is not None:
            if caps.supports_resolution:
                result.resolution = resolution
            else:
                ignored.append(OverrideIgnored(key="resolution", value=resolution))
    if enable_audio is not None:
        if caps.supports_audio:
            result.enable_audio = enable_audio
        else:
            ignored.append(OverrideIgnored(key="enable_audio", value=enable_audio))

    if reference_images:
        if caps.max_input_images > 0:
            result.reference_images = reference_images[: caps.max_input_images]
            if len(reference_images) > caps.max_input_images:
                logger.warning(
                    "Provider '%s' supports max %d input images, truncating from %d",
                    provider_id,
                    caps.max_input_images,
                    len(reference_images),
                )
        else:
            ignored.append(
                OverrideIgnored(
                    key="reference_images",
                    value=f"{len(reference_images)} image(s)",
                )
            )
    if reference_videos:
        if caps.max_input_videos > 0:
            result.reference_videos = reference_videos[: caps.max_input_videos]
        else:
            ignored.append(
                OverrideIgnored(
                    key="reference_videos",
                    value=f"{len(reference_videos)} video(s)",
                )
            )

    if ignored:
        logger.info(
            "Provider '%s' ignored overrides: %s",
            provider_id,
            ", ".join(f"{o.key}={o.value}" for o in ignored),
        )
    if normalizations:
        logger.info(
            "Provider '%s' normalized params: %s",
            provider_id,
            ", ".join(f"{n.field}: {n.requested} → {n.applied}" for n in normalizations),
        )

    return result, ignored, normalizations


__all__ = ["SanitizedOverrides", "sanitize_overrides"]
