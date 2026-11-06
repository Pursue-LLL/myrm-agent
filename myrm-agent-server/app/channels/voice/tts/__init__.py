"""[INPUT]
- app.channels.voice.tts.common::EDGE_TTS_INSTALL_HINT / _resolve_base_url / _summarize_for_tts / _write_temp / is_edge_tts_available / is_local_tts_available / is_piper_available (POS: voice tts 子包的一部分；由 __init__.py 聚合导出。)
- app.channels.voice.tts.core::synthesize / synthesize_stream (POS: voice tts 子包的一部分；由 __init__.py 聚合导出。)
- app.channels.voice.tts.providers::_elevenlabs_request / _fish_audio_request / _minimax_request / _openai_request (POS: voice tts 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- EDGE_TTS_INSTALL_HINT
- _resolve_base_url
- _summarize_for_tts
- _write_temp
- is_edge_tts_available
- is_local_tts_available
- is_piper_available
- synthesize
- synthesize_stream
- _elevenlabs_request
- _fish_audio_request
- _minimax_request
- _openai_request

[POS]
`app.channels.voice.tts` 的唯一入口；实现按 common/core/providers 分层。
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
