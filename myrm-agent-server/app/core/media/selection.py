"""Whether the user has picked something the media engines can run.

[INPUT]
- myrm_agent_harness.toolkits.llms.image.types::get_profile (POS: image model catalog)
- myrm_agent_harness.toolkits.llms.video::get_registry (POS: video provider registry with each provider's models)
- myrm_agent_harness.toolkits.llms.tts.models::SUPPORTED_TTS_PROVIDERS (POS: TTS providers the engine calls)

[OUTPUT]
- is_image_model_selected(): the image model is in the catalog
- is_video_selected(): the video provider is registered and serves the model
- is_tts_selected(): provider, model and voice are all chosen and the provider is one the engine calls

[POS]
The single definition of "selected". A media tool is mounted only when the user's own choice names something the
engine can run, so an empty selection, or a retired model that is no longer in the catalog, never gets a default
substituted: the tool is simply absent until the user chooses again.
"""

from __future__ import annotations

from typing import TypeGuard

from myrm_agent_harness.toolkits.llms.image.types import get_profile
from myrm_agent_harness.toolkits.llms.tts.models import SUPPORTED_TTS_PROVIDERS
from myrm_agent_harness.toolkits.llms.video import get_registry


def is_image_model_selected(model: str | None) -> TypeGuard[str]:
    return model is not None and get_profile(model) is not None


def is_video_selected(provider: str | None, model: str | None) -> bool:
    return provider is not None and model is not None and get_registry().serves(provider, model)


def is_tts_selected(provider: str | None, model: str | None, voice: str | None) -> bool:
    return bool(model) and bool(voice) and provider in SUPPORTED_TTS_PROVIDERS
