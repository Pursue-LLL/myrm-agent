"""sanitize_overrides fits a request to what a provider declares it can honour."""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms._media_shared.types import (
    ModeCapabilities,
    NormalizationRecord,
    ProviderModeCapabilities,
    SizeSpec,
)
from myrm_agent_harness.toolkits.llms.video._overrides import SanitizedOverrides, sanitize_overrides
from myrm_agent_harness.toolkits.llms.video.models import OverrideIgnored, ProviderCapabilities

_FRAME = b"frame"
_CLIP = b"clip"


def _sanitize(
    caps: ProviderCapabilities,
    *,
    duration_seconds: int | None = None,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    enable_audio: bool | None = None,
    reference_images: list[bytes] | None = None,
    reference_videos: list[bytes] | None = None,
) -> tuple[SanitizedOverrides, list[OverrideIgnored], list[NormalizationRecord]]:
    sanitized, ignored, normalizations = sanitize_overrides(
        caps,
        provider_id="demo",
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        enable_audio=enable_audio,
        reference_images=reference_images,
        reference_videos=reference_videos,
    )
    return sanitized, ignored, list(normalizations)


class TestProviderWithoutModeCapabilities:
    def test_a_request_the_provider_fully_supports_passes_through(self) -> None:
        caps = ProviderCapabilities(
            supports_aspect_ratio=True,
            supports_resolution=True,
            supports_audio=True,
            max_input_images=2,
            max_input_videos=1,
        )

        sanitized, ignored, normalizations = _sanitize(
            caps,
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution="720p",
            enable_audio=True,
            reference_images=[_FRAME],
            reference_videos=[_CLIP],
        )

        assert sanitized == SanitizedOverrides(
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution="720p",
            enable_audio=True,
            reference_images=[_FRAME],
            reference_videos=[_CLIP],
        )
        assert ignored == []
        assert normalizations == []

    def test_what_the_provider_does_not_take_is_dropped_and_reported(self) -> None:
        sanitized, ignored, _ = _sanitize(
            ProviderCapabilities(),
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution="720p",
            enable_audio=False,
            reference_images=[_FRAME, _FRAME],
            reference_videos=[_CLIP],
        )

        assert sanitized == SanitizedOverrides(duration_seconds=5)
        assert ignored == [
            OverrideIgnored(key="aspect_ratio", value="16:9"),
            OverrideIgnored(key="resolution", value="720p"),
            OverrideIgnored(key="enable_audio", value=False),
            OverrideIgnored(key="reference_images", value="2 image(s)"),
            OverrideIgnored(key="reference_videos", value="1 video(s)"),
        ]

    def test_references_beyond_the_provider_limit_are_truncated(self) -> None:
        caps = ProviderCapabilities(max_input_images=1, max_input_videos=1)

        sanitized, ignored, _ = _sanitize(caps, reference_images=[b"a", b"b"], reference_videos=[b"x", b"y"])

        assert sanitized.reference_images == [b"a"]
        assert sanitized.reference_videos == [b"x"]
        assert ignored == []

    def test_nothing_requested_is_nothing_sent(self) -> None:
        sanitized, ignored, normalizations = _sanitize(ProviderCapabilities(supports_audio=True))

        assert sanitized == SanitizedOverrides()
        assert ignored == []
        assert normalizations == []


class TestProviderWithModeCapabilities:
    def test_the_requested_ratio_and_duration_snap_to_the_closest_supported_values(self) -> None:
        modes = ProviderModeCapabilities(
            generate=ModeCapabilities(
                supported_aspect_ratios=("16:9", "9:16"),
                supported_sizes=(SizeSpec(1280, 720),),
                supported_durations=(5, 10),
            )
        )
        caps = ProviderCapabilities(mode_capabilities=modes, supports_resolution=True)

        sanitized, _, normalizations = _sanitize(caps, duration_seconds=7, aspect_ratio="4:3")

        assert sanitized == SanitizedOverrides(duration_seconds=5, aspect_ratio="16:9", resolution="1280x720")
        assert [(r.field, r.requested, r.applied) for r in normalizations] == [
            ("aspect_ratio", "4:3", "16:9"),
            ("duration_seconds", "7", "5"),
        ]

    def test_reference_inputs_pick_the_mode_that_declares_them(self) -> None:
        modes = ProviderModeCapabilities(
            generate=ModeCapabilities(supported_durations=(5,)),
            image_to_video=ModeCapabilities(supported_durations=(10,)),
            video_to_video=ModeCapabilities(supported_durations=(15,)),
        )
        caps = ProviderCapabilities(mode_capabilities=modes, max_input_images=1, max_input_videos=1)

        text_only, _, _ = _sanitize(caps, duration_seconds=11)
        with_image, _, _ = _sanitize(caps, duration_seconds=11, reference_images=[_FRAME])
        with_video, _, _ = _sanitize(caps, duration_seconds=11, reference_images=[_FRAME], reference_videos=[_CLIP])

        assert text_only.duration_seconds == 5
        assert with_image.duration_seconds == 10
        assert with_video.duration_seconds == 15

    def test_references_are_still_sent_when_only_the_text_mode_is_declared(self) -> None:
        modes = ProviderModeCapabilities(generate=ModeCapabilities(supported_durations=(5,)))
        caps = ProviderCapabilities(mode_capabilities=modes, max_input_images=1)

        sanitized, _, _ = _sanitize(caps, duration_seconds=11, reference_images=[_FRAME])

        assert sanitized.duration_seconds == 5
        assert sanitized.reference_images == [_FRAME]
