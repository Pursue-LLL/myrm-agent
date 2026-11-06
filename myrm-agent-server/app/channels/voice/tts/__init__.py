"""语音合成门面。

[OUTPUT]
synthesize / synthesize_stream / is_*_available / 提供方辅助函数与安装提示。

[POS]
`app.channels.voice.tts` 的唯一入口；实现按 common/core/providers 拆分。
"""

from app.channels.voice.tts.common import (
    EDGE_TTS_INSTALL_HINT,
    _resolve_base_url,
    _summarize_for_tts,
    _write_temp,
    is_edge_tts_available,
    is_local_tts_available,
    is_piper_available,
)
from app.channels.voice.tts.core import synthesize, synthesize_stream
from app.channels.voice.tts.providers import (
    _elevenlabs_request,
    _fish_audio_request,
    _minimax_request,
    _openai_request,
)

__all__ = [
    "EDGE_TTS_INSTALL_HINT",
    "_elevenlabs_request",
    "_fish_audio_request",
    "_minimax_request",
    "_openai_request",
    "_resolve_base_url",
    "_summarize_for_tts",
    "_write_temp",
    "is_edge_tts_available",
    "is_local_tts_available",
    "is_piper_available",
    "synthesize",
    "synthesize_stream",
]
