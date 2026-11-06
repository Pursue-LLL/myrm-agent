"""TTS 共享常量、可用性探测与临时文件辅助。

[POS]
voice tts 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from types import ModuleType

from app.channels.types import VoiceConfig
from app.core.utils.chat_utils import extract_litellm_answer_text

logger = logging.getLogger(__name__)


_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "elevenlabs": "https://api.elevenlabs.io",
    "fish_audio": "https://api.fish.audio/v1",
    "minimax": "https://api.minimax.io/v1",
    "voicebox": "http://127.0.0.1:8000",
}

_DEFAULT_VOICES: dict[str, str] = {
    "openai": "alloy",
    "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
    "fish_audio": "7f92f8afb8ec43bf81429cc1c9199cb1",
    "minimax": "English_expressive_narrator",
    "edge": "en-US-MichelleNeural",
    "piper": "en_US-lessac-medium",
    "voicebox": "default",
}


def _resolve_base_url(config: VoiceConfig, provider: str) -> str:
    """Resolve the API base URL: config override (OpenAI & Voicebox) > provider default."""
    if provider in ("openai", "voicebox") and config.tts_base_url:
        return config.tts_base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(provider, "")


_MIN_TEXT_LENGTH = 10
_TTS_TIMEOUT = 30.0
_STREAM_CHUNK_SIZE = 4096
_EDGE_TTS_INSTALL_HINT = "uv sync --extra voice-tts"
EDGE_TTS_INSTALL_HINT = _EDGE_TTS_INSTALL_HINT


_PIPER_INSTALL_HINT = "uv sync --extra voice-tts-local"
PIPER_INSTALL_HINT = _PIPER_INSTALL_HINT


def is_piper_available() -> bool:
    """Return whether the optional local Piper TTS engine is installed."""
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


def is_local_tts_available() -> bool:
    """Return whether any fully offline local TTS provider (Piper) is available."""
    return is_piper_available()


def is_edge_tts_available() -> bool:
    """Return whether the optional Edge TTS (GPL-3.0) package is installed."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def _import_edge_tts() -> ModuleType:
    """Import edge_tts or raise with an install hint."""
    try:
        import edge_tts
    except ImportError as exc:
        raise ImportError(f"edge-tts is not installed. Install with: {_EDGE_TTS_INSTALL_HINT}") from exc
    return edge_tts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _write_temp(data: bytes, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


_SUMMARY_PROMPT = (
    "Summarize the following text for audio playback. "
    "Keep key information, be concise, and stay under 300 words. "
    "Output the summary directly without any preamble.\n\n"
)

_SUMMARY_TIMEOUT = 15.0


async def _summarize_for_tts(text: str, config: VoiceConfig) -> str | None:
    """Summarize long text using LLM before TTS synthesis."""
    try:
        from litellm import acompletion

        model = config.tts_summary_model or "gpt-4o-mini"
        resp = await acompletion(
            model=model,
            messages=[{"role": "user", "content": f"{_SUMMARY_PROMPT}{text}"}],
            max_tokens=500,
            temperature=0.3,
            timeout=_SUMMARY_TIMEOUT,
        )
        summary = extract_litellm_answer_text(resp).strip()
        if not summary:
            return None

        logger.warning("TTS: summarized %d → %d chars (model=%s)", len(text), len(summary), model)
        return summary
    except Exception:
        logger.exception("TTS: summarization failed, using original text")
        return None
