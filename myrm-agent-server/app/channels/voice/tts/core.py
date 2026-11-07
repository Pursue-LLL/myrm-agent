"""[INPUT]
- app.channels.types::VoiceConfig (POS: Channel system domain types — pure data definitions, no I/O.)
- app.channels.voice.tts.common::_EDGE_TTS_INSTALL_HINT / _MIN_TEXT_LENGTH / _summarize_for_tts / is_edge_tts_available (POS: voice tts 子包的一部分；由 __init__.py 聚合导出。)
- app.channels.voice.tts.providers::_STREAM_PROVIDERS / _stream_edge / _synthesize_api / _synthesize_edge (POS: voice tts 子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- synthesize: Synthesize text to an audio file. Falls back to Edge TTS on failure.
- synthesize_stream: Stream-synthesize text to MP3 audio chunks. Falls back to Edge TTS.

[POS]
voice tts 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from app.channels.types import VoiceConfig

from .common import (
    _EDGE_TTS_INSTALL_HINT,
    _MIN_TEXT_LENGTH,
    _summarize_for_tts,
    is_edge_tts_available,
)
from .providers import (
    _STREAM_PROVIDERS,
    _stream_edge,
    _synthesize_api,
    _synthesize_edge,
)

logger = logging.getLogger(__name__)


async def synthesize(
    text: str,
    config: VoiceConfig,
    *,
    output_format: str = "mp3",
) -> Path | None:
    """Synthesize text to an audio file. Falls back to Edge TTS on failure."""
    if len(text) < _MIN_TEXT_LENGTH:
        logger.warning("TTS: text too short (%d chars), skipping", len(text))
        return None

    if len(text) > config.tts_max_length:
        logger.warning("TTS: text too long (%d > %d chars), skipping", len(text), config.tts_max_length)
        return None

    if config.tts_summary_enabled and len(text) > config.tts_summary_threshold:
        summarized = await _summarize_for_tts(text, config)
        if summarized:
            text = summarized

    provider = config.tts_provider.lower()
    try:
        if provider == "edge":
            return await _synthesize_edge(text, config)
        return await _synthesize_api(text, config, provider, output_format)
    except ImportError:
        logger.warning("TTS: edge-tts not installed (%s)", _EDGE_TTS_INSTALL_HINT)
        return None
    except Exception:
        logger.exception("TTS: primary provider '%s' failed", provider)

    if provider != "edge":
        if not is_edge_tts_available():
            logger.warning(
                "TTS: Edge TTS fallback unavailable (install voice-tts extra: %s)",
                _EDGE_TTS_INSTALL_HINT,
            )
        else:
            try:
                logger.warning("TTS: falling back to Edge TTS (free)")
                return await _synthesize_edge(text, config)
            except Exception:
                logger.exception("TTS: Edge TTS fallback also failed")
    return None


async def synthesize_stream(
    text: str,
    config: VoiceConfig,
) -> AsyncGenerator[bytes]:
    """Stream-synthesize text to MP3 audio chunks. Falls back to Edge TTS."""
    if len(text) < _MIN_TEXT_LENGTH:
        logger.warning("TTS stream: text too short (%d chars), skipping", len(text))
        return

    provider = config.tts_provider.lower()
    stream_fn = _STREAM_PROVIDERS.get(provider)

    if stream_fn:
        try:
            async for chunk in stream_fn(text, config):
                yield chunk
            return
        except ImportError:
            logger.warning("TTS stream: edge-tts not installed (%s)", _EDGE_TTS_INSTALL_HINT)
            return
        except Exception:
            logger.exception("TTS stream: provider '%s' failed, falling back", provider)

    if provider != "edge":
        if is_edge_tts_available():
            try:
                async for chunk in _stream_edge(text, config):
                    yield chunk
                return
            except Exception:
                logger.exception("TTS stream: edge fallback also failed")
        else:
            logger.warning(
                "TTS stream: Edge TTS fallback unavailable (install voice-tts extra: %s)",
                _EDGE_TTS_INSTALL_HINT,
            )


# ---------------------------------------------------------------------------
# Request builders (shared between streaming and non-streaming)
# ---------------------------------------------------------------------------
