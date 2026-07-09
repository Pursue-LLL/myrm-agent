"""SILK audio codec for WeChat voice messages.

WeChat uses SILK v3 encoding for voice messages. This module converts
SILK → WAV for STT processing (Whisper/Groq/Deepgram).

[INPUT]

[OUTPUT]
- silk_to_wav: Convert WeChat SILK file to WAV format (requires optional `pilk` / extra `wechat-silk`)

[POS]
WeChat voice format converter. Converts SILK-encoded voice files to WAV format.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def silk_to_wav(silk_path: Path, wav_path: Path, sample_rate: int = 24000) -> bool:
    """Convert WeChat SILK audio to WAV format.

    Args:
        silk_path: Input SILK file path.
        wav_path: Output WAV file path.
        sample_rate: Target sample rate (default 24000 Hz for Whisper).

    Returns:
        True if conversion succeeded.
    """
    try:
        import pilk

        pilk.silk_to_wav(str(silk_path), str(wav_path), sample_rate)
        return wav_path.exists()
    except (ImportError, TypeError):
        logger.warning(
            "pilk not installed — SILK audio conversion unavailable. "
            "Install: uv sync --extra wechat-silk"
        )
        return False
    except Exception as exc:
        logger.warning("SILK decode failed: %s", exc)
        return False
