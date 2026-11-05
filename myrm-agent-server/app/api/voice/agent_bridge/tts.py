"""[INPUT]
- .common (POS: shared types and constants)

[OUTPUT]
- TtsMixin

[POS]
Voice bridge mixin: TTS segment streaming and interruption bookkeeping.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .common import (
    _FALLBACK_EN,
    _FALLBACK_ZH,
    _INTERRUPT_TTL_S,
    _SPEECH_INTERRUPTED_NOTE,
    _WORKING_HINT_EN,
    _WORKING_HINT_ZH,
    logger,
)


class TtsMixin:
    async def _stream_tts_segment(self, text: str, turn_id: str) -> None:
        """Stream a single TTS segment to the client."""
        if self._tts_cancel_event.is_set() or self._current_turn != turn_id:
            return

        from app.channels.voice.tts import synthesize_stream

        try:
            from fastapi import WebSocketDisconnect

            await self._send_json({"type": "tts_start"})
            async for chunk in synthesize_stream(text, self._voice_config):
                if self._tts_cancel_event.is_set() or self._current_turn != turn_id:
                    break
                try:
                    async with self._ws_send_lock:
                        await self._ws.send_bytes(chunk)
                except (WebSocketDisconnect, RuntimeError):
                    self._closed = True
                    break
            await self._send_json({"type": "tts_end"})
        except Exception:
            logger.warning("Voice bridge TTS segment error", exc_info=True)

    async def _tts_working_hint(self) -> None:
        """Speak a brief working hint while Agent processes."""
        lang = (self._voice_config.stt_language or "").lower()
        hint = _WORKING_HINT_ZH if "zh" in lang or "cn" in lang else _WORKING_HINT_EN
        await self._stream_tts_segment(hint, self._current_turn or "")

    async def _speak_fallback(self) -> None:
        """Speak a fallback message when Agent fails."""
        lang = (self._voice_config.stt_language or "").lower()
        msg = _FALLBACK_ZH if "zh" in lang or "cn" in lang else _FALLBACK_EN
        await self._stream_tts_segment(msg, self._current_turn or "")
        await self._send_json({"type": "agent_error", "message": "Agent execution failed"})

    def cancel_tts(self) -> None:
        """Signal TTS cancellation (barge-in) and mark interrupted latch."""
        self._tts_cancel_event.set()
        self._speech_interrupted_at = time.monotonic()

    def _take_speech_interrupted(self) -> str:
        """Consume the interrupted latch if within TTL; return note prefix or empty."""
        at = self._speech_interrupted_at
        self._speech_interrupted_at = None
        if at is not None and (time.monotonic() - at) < _INTERRUPT_TTL_S:
            return _SPEECH_INTERRUPTED_NOTE + "\n"
        return ""
