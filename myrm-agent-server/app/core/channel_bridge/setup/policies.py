"""反应策略、贴纸视觉与语音配置加载。

[POS]
channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.channel_bridge import channel_gateway

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.channels.media.sticker_vision import StickerVisionService
    from app.channels.routing.router_models import (
        ReactionPolicy,
    )
    from app.channels.types import VoiceConfig


async def refresh_reaction_policy() -> None:
    """Reload reaction policy from DB and apply to the running AgentRouter."""
    policy = await _load_reaction_policy()
    channel_gateway.set_reaction_policy(policy)


async def _load_reaction_policy() -> ReactionPolicy:
    """Load ReactionPolicy from the channels config."""
    from app.channels.routing.router_models import (
        ReactionPolicy,
    )
    from app.channels.types import ReactionLevel
    from app.core.channel_bridge.credential_spec import load_from_db

    _defaults = ReactionPolicy()
    try:
        creds = await load_from_db("channels")
        if not creds:
            return _defaults

        level = _defaults.level
        raw_level = creds.get("reactionLevel")
        if isinstance(raw_level, str) and raw_level in {e.value for e in ReactionLevel}:
            level = ReactionLevel(raw_level)

        processing = _defaults.processing_emoji
        raw_proc = creds.get("processingEmoji")
        if isinstance(raw_proc, str) and raw_proc.strip():
            processing = raw_proc.strip()

        completion = _defaults.completion_emoji
        raw_comp = creds.get("completionEmoji")
        if isinstance(raw_comp, str) and raw_comp.strip():
            completion = raw_comp.strip()

        failure = _defaults.failure_emoji
        raw_fail = creds.get("failureEmoji")
        if isinstance(raw_fail, str) and raw_fail.strip():
            failure = raw_fail.strip()

        return ReactionPolicy(
            level=level,
            processing_emoji=processing,
            completion_emoji=completion,
            failure_emoji=failure,
        )
    except Exception:
        return _defaults


async def _load_sticker_vision_service() -> StickerVisionService | None:
    """Create StickerVisionService from user's visionFallbackModel config.

    Returns None if vision fallback model is not configured.
    """
    try:
        from app.channels.media.sticker_vision import StickerVisionService
        from app.core.channel_bridge.config_loader import _load_single_config
        from app.core.channel_bridge.config_parsers import build_vision_fallback_engine_from_providers

        providers_dict_raw = await _load_single_config("providers")
        if not isinstance(providers_dict_raw, dict):
            return None

        engine = build_vision_fallback_engine_from_providers(providers_dict_raw)
        if engine is None:
            return None

        svc = StickerVisionService(engine)
        logger.info("Sticker vision enabled with ordered vision fallback chain")
        return svc
    except Exception:
        logger.warning("Failed to load sticker vision service, stickers will use emoji only")
        return None


async def _load_voice_config() -> VoiceConfig | None:
    """Load VoiceConfig from the admin user's UserConfig table."""
    try:
        from app.core.channel_bridge.config_loader import load_voice_config_only
        from app.core.channel_bridge.config_parsers import extract_voice_config

        voice_dict = await load_voice_config_only()
        voice = extract_voice_config(voice_dict)
        if voice:
            logger.info("Voice config loaded: STT=%s TTS=%s", voice.stt_enabled, voice.tts_mode)
        return voice
    except Exception:
        logger.exception("Failed to load voice config")
        return None
