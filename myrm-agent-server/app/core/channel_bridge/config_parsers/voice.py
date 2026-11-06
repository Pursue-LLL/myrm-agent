"""[INPUT]
- app.channels.types::TTSMode (POS: Channel system domain types — pure data definitions, no I/O.)
- app.core.channel_bridge.config_parsers.common::_float_setting / _int_setting (POS: channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。)

[OUTPUT]
- _build_voice_config_from_dict: Build VoiceConfig from the frontend voice settings dict.
- extract_voice_config: Extract VoiceConfig from the frontend's voice settings.
- extract_web_tts_config: Extract VoiceConfig for Web UI read-aloud (/tts API).

[POS]
channel_bridge 配置解析包的子模块；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.types import TTSMode

if TYPE_CHECKING:
    from app.channels.types import VoiceConfig

from app.core.channel_bridge.config_parsers.common import _float_setting, _int_setting

logger = logging.getLogger(__name__)


def _build_voice_config_from_dict(voice_dict: dict[str, object]) -> "VoiceConfig":
    """Build VoiceConfig from the frontend voice settings dict."""
    from app.channels.types import VoiceConfig

    stt_enabled = bool(voice_dict.get("sttEnabled", False))
    tts_mode_raw = str(voice_dict.get("ttsMode", "off")).lower()
    tts_mode = TTSMode(tts_mode_raw) if tts_mode_raw in ("off", "always", "inbound") else TTSMode.OFF
    stt_language = voice_dict.get("sttLanguage")

    return VoiceConfig(
        stt_enabled=stt_enabled,
        stt_provider=str(voice_dict.get("sttProvider", "openai")),
        stt_api_key=str(voice_dict.get("sttApiKey", "")),
        stt_model=str(voice_dict.get("sttModel", "whisper-1")),
        stt_language=stt_language if isinstance(stt_language, str) else None,
        stt_local_model=str(voice_dict.get("sttLocalModel", "base")),
        stt_local_device=str(voice_dict.get("sttLocalDevice", "auto")),
        stt_local_compute_type=str(voice_dict.get("sttLocalComputeType", "auto")),
        stt_base_url=str(voice_dict.get("sttBaseUrl", "")),
        tts_mode=tts_mode,
        tts_provider=str(voice_dict.get("ttsProvider", "edge")),
        tts_api_key=str(voice_dict.get("ttsApiKey", "")),
        tts_base_url=str(voice_dict.get("ttsBaseUrl", "")),
        tts_voice=str(voice_dict.get("ttsVoice", "")),
        tts_speed=_float_setting(voice_dict.get("ttsSpeed", 1.0), 1.0),
        tts_pitch=_float_setting(voice_dict.get("ttsPitch", 0.0), 0.0),
        tts_max_length=_int_setting(voice_dict.get("ttsMaxLength", 4000), 4000),
        tts_summary_enabled=bool(voice_dict.get("ttsSummaryEnabled", True)),
        tts_summary_threshold=_int_setting(voice_dict.get("ttsSummaryThreshold", 1500), 1500),
        tts_summary_model=str(voice_dict.get("ttsSummaryModel", "")),
    )


def extract_voice_config(voice_dict: dict[str, object] | None) -> "VoiceConfig | None":
    """Extract VoiceConfig from the frontend's voice settings.

    Returns None if voice is not configured (STT/TTS both disabled).
    """
    if not voice_dict:
        return None

    built = _build_voice_config_from_dict(voice_dict)
    if not built.stt_enabled and built.tts_mode == TTSMode.OFF:
        return None

    return built


def extract_web_tts_config(
    voice_dict: dict[str, object] | None,
) -> "VoiceConfig | None":
    """Extract VoiceConfig for Web UI read-aloud (/tts API).

    Unlike extract_voice_config, does not require ttsMode != off or sttEnabled.
    Channel outbound TTS still uses extract_voice_config.
    """
    if not voice_dict:
        return None
    return _build_voice_config_from_dict(voice_dict)
