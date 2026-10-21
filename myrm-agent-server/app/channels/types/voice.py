"""Voice STT/TTS configuration and result types.

[INPUT]
- (none)

[OUTPUT]
- VoiceConfig: combined STT + TTS configuration injected by the business layer
- TTSMode: when Agent replies are converted to audio
- STTResult: speech-to-text transcription result

[POS]
Voice pipeline configuration types consumed by channel providers; zero I/O,
pure data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TTSMode(StrEnum):
    """Controls when Agent replies are converted to audio."""

    OFF = "off"
    ALWAYS = "always"
    INBOUND = "inbound"


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    """Combined STT + TTS configuration injected by the business layer.

    STT: transcribes inbound voice messages to text before Agent processing.
    TTS: converts Agent text replies to audio before sending.
    """

    stt_enabled: bool = False
    stt_provider: str = "openai"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    stt_language: str | None = None

    stt_local_model: str = "base"
    stt_local_device: str = "auto"
    stt_local_compute_type: str = "auto"
    stt_base_url: str = ""

    tts_mode: TTSMode = TTSMode.OFF
    tts_provider: str = "edge"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = ""
    tts_speed: float = 1.0
    tts_pitch: float = 0.0
    tts_max_length: int = 4000

    tts_summary_enabled: bool = True
    tts_summary_threshold: int = 1500
    tts_summary_model: str = ""


@dataclass(frozen=True, slots=True)
class STTResult:
    """Result of speech-to-text transcription."""

    text: str
    language: str | None = None
    duration: float | None = None
