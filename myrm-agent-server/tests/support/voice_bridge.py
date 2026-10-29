"""A voice agent bridge on a mocked WebSocket, shared by the bridge unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

from app.api.voice.agent_bridge import VoiceAgentBridge


@dataclass(frozen=True, slots=True)
class FakeVoiceConfig:
    stt_enabled: bool = True
    stt_provider: str = "deepgram"
    stt_api_key: str = "k"
    stt_model: str = "nova-3"
    stt_language: str | None = "en"
    tts_mode: str = "always"
    tts_provider: str = "edge"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = "en-US-GuyNeural"
    camera_enabled: bool = False
    full_duplex: bool = True


def make_bridge(ws: AsyncMock | None = None) -> VoiceAgentBridge:
    mock_ws = ws or AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.send_bytes = AsyncMock()
    return VoiceAgentBridge(
        _ws=mock_ws,
        _voice_config=FakeVoiceConfig(),  # type: ignore[arg-type]
        _agent_id="test-agent",
        _chat_id="test-chat",
    )
