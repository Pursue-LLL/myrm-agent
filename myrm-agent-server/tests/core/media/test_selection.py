"""A media tool exists only when the user picked something the engine can run."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.llms.image.types import BUILTIN_PROFILES
from myrm_agent_harness.toolkits.llms.tts.models import SUPPORTED_TTS_PROVIDERS
from myrm_agent_harness.toolkits.llms.video import get_registry

from app.core.media.selection import is_image_model_selected, is_tts_selected, is_video_selected


def _video_choices() -> list[tuple[str, str]]:
    """Every (provider, model) pair the video registry serves."""
    registry = get_registry()
    choices: list[tuple[str, str]] = []
    for info in registry.list_providers():
        provider = registry.get(str(info["id"]))
        assert provider is not None
        choices.extend((provider.provider_id, model.id) for model in provider.supported_models)
    return choices


_VIDEO_CHOICES = _video_choices()


@pytest.mark.parametrize("model", sorted(BUILTIN_PROFILES))
def test_every_catalog_image_model_counts_as_selected(model: str) -> None:
    assert is_image_model_selected(model)


@pytest.mark.parametrize("model", [None, "", " ", "dall-e-3", "gpt-image-1", "GPT-IMAGE-2.6-SUNBURST", "sunburst"])
def test_an_empty_or_retired_image_model_is_not_selected(model: str | None) -> None:
    assert not is_image_model_selected(model)


@pytest.mark.parametrize(("provider", "model"), _VIDEO_CHOICES)
def test_every_model_a_registered_provider_lists_counts_as_selected(provider: str, model: str) -> None:
    assert is_video_selected(provider, model)


@pytest.mark.parametrize(
    ("provider", "model"),
    [(None, None), ("gemini", None), (None, "veo"), ("", ""), ("sora", "sora-2"), ("openai", "sora-2"), ("gemini", "sora-2")],
)
def test_a_missing_retired_or_mismatched_video_choice_is_not_selected(provider: str | None, model: str | None) -> None:
    assert not is_video_selected(provider, model)


def test_a_model_of_another_provider_is_not_selected() -> None:
    (provider, model) = _VIDEO_CHOICES[0]
    other = next(candidate for candidate, _ in _VIDEO_CHOICES if candidate != provider)

    assert not is_video_selected(other, model)


@pytest.mark.parametrize("provider", sorted(SUPPORTED_TTS_PROVIDERS))
def test_a_supported_provider_with_a_model_and_a_voice_counts_as_selected(provider: str) -> None:
    assert is_tts_selected(provider, "some-model", "some-voice")


@pytest.mark.parametrize(
    ("provider", "model", "voice"),
    [
        (None, "m", "v"),
        ("", "m", "v"),
        ("edge", "m", "v"),
        ("piper", "m", "v"),
        ("openai", None, "v"),
        ("openai", "", "v"),
        ("openai", "m", None),
        ("openai", "m", ""),
        (None, None, None),
    ],
)
def test_a_missing_part_or_an_unsupported_provider_is_not_selected(
    provider: str | None, model: str | None, voice: str | None
) -> None:
    assert not is_tts_selected(provider, model, voice)
