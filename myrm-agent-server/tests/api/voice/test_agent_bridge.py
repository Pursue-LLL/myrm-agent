"""Unit tests for voice agent bridge (agent_bridge.py).

Covers:
  - _extract_speakable_segments: sentence splitting
  - _log_turn_latency: latency logging format
  - VoiceAgentBridge: cancel_tts, _cancel_current_turn, _send_json error handling
  - VoiceAgentBridge.handle_stt_final: turn lifecycle with mocked dependencies

Approval handling is in test_agent_bridge_approval.py; params and the fast lane in test_agent_bridge_fast_lane.py.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.voice.agent_bridge import (
    _extract_speakable_segments,
    _log_turn_latency,
)
from tests.support.voice_bridge import make_bridge


class TestExtractSpeakableSegments:
    def test_single_sentence(self) -> None:
        segments, remaining = _extract_speakable_segments("Hello world.")
        assert segments == ["Hello world."]
        assert remaining == ""

    def test_multiple_sentences(self) -> None:
        segments, remaining = _extract_speakable_segments("First. Second! Third?")
        assert segments == ["First.", "Second!", "Third?"]
        assert remaining == ""

    def test_chinese_punctuation(self) -> None:
        segments, remaining = _extract_speakable_segments("你好。世界！")
        assert segments == ["你好。", "世界！"]
        assert remaining == ""

    def test_incomplete_sentence(self) -> None:
        segments, remaining = _extract_speakable_segments("Hello world")
        assert segments == []
        assert remaining == "Hello world"

    def test_mixed_complete_and_incomplete(self) -> None:
        segments, remaining = _extract_speakable_segments("First. Second")
        assert segments == ["First."]
        assert remaining == " Second"

    def test_empty_string(self) -> None:
        segments, remaining = _extract_speakable_segments("")
        assert segments == []
        assert remaining == ""

    def test_newline_as_boundary(self) -> None:
        segments, remaining = _extract_speakable_segments("Line one\nLine two")
        assert segments == ["Line one"]
        assert remaining == "Line two"


# ── _log_turn_latency tests ───────────────────────────────────────────


class TestLogTurnLatency:
    def test_full_latency_log(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="app.api.voice.agent_bridge"):
            _log_turn_latency("turn-abc", "ok", 0.0, 0.1, 3.2)

        assert len(caplog.records) == 1
        msg = caplog.records[0].message
        assert "turn=turn-abc" in msg
        assert "outcome=ok" in msg
        assert "total=3200ms" in msg
        assert "params_assembly=100ms" in msg
        assert "agent_tts=3100ms" in msg

    def test_params_failed(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="app.api.voice.agent_bridge"):
            _log_turn_latency("turn-xyz", "params_failed", 0.0, None, 0.5)

        msg = caplog.records[0].message
        assert "outcome=params_failed" in msg
        assert "total=500ms" in msg
        assert "params_assembly" not in msg
        assert "agent_tts" not in msg


class TestVoiceAgentBridgeSendJson:
    @pytest.mark.asyncio
    async def test_send_json_success(self) -> None:
        ws = AsyncMock()
        bridge = make_bridge(ws)
        await bridge._send_json({"type": "test"})
        ws.send_text.assert_awaited_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "test"

    @pytest.mark.asyncio
    async def test_send_json_error_sets_closed(self) -> None:
        ws = AsyncMock()
        bridge = make_bridge(ws)
        ws.send_text.side_effect = RuntimeError("WS closed")
        await bridge._send_json({"type": "test"})
        assert bridge._closed is True

    @pytest.mark.asyncio
    async def test_send_json_skips_when_closed(self) -> None:
        ws = AsyncMock()
        bridge = make_bridge(ws)
        bridge._closed = True
        await bridge._send_json({"type": "test"})
        ws.send_text.assert_not_awaited()


class TestVoiceAgentBridgeCancelTts:
    def test_cancel_tts_sets_event(self) -> None:
        bridge = make_bridge()
        assert not bridge._tts_cancel_event.is_set()
        bridge.cancel_tts()
        assert bridge._tts_cancel_event.is_set()

    def test_cancel_tts_sets_interrupted_latch(self) -> None:
        bridge = make_bridge()
        assert bridge._speech_interrupted_at is None
        bridge.cancel_tts()
        assert bridge._speech_interrupted_at is not None

    def test_cancel_current_turn(self) -> None:
        bridge = make_bridge()
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

        token = CancellationToken()
        bridge._cancel_token = token
        bridge._current_turn = "turn-1"

        bridge._cancel_current_turn()

        assert token.is_cancelled
        assert bridge._current_turn is None
        assert bridge._cancel_token is None
        assert bridge._tts_cancel_event.is_set()


class TestSpeechInterruptedLatch:
    """Tests for the speech-interrupted latch (R16)."""

    def test_take_returns_note_when_latch_fresh(self) -> None:
        import time

        from app.api.voice.agent_bridge import _SPEECH_INTERRUPTED_NOTE

        bridge = make_bridge()
        bridge._speech_interrupted_at = time.monotonic()

        result = bridge._take_speech_interrupted()
        assert result == _SPEECH_INTERRUPTED_NOTE + "\n"
        assert bridge._speech_interrupted_at is None

    def test_take_returns_empty_when_no_latch(self) -> None:
        bridge = make_bridge()
        result = bridge._take_speech_interrupted()
        assert result == ""

    def test_take_returns_empty_when_latch_expired(self) -> None:
        import time

        bridge = make_bridge()
        bridge._speech_interrupted_at = time.monotonic() - 200.0

        result = bridge._take_speech_interrupted()
        assert result == ""
        assert bridge._speech_interrupted_at is None

    def test_take_is_one_shot(self) -> None:
        """Latch is consumed on first take; second take returns empty."""
        import time

        bridge = make_bridge()
        bridge._speech_interrupted_at = time.monotonic()

        first = bridge._take_speech_interrupted()
        second = bridge._take_speech_interrupted()
        assert first != ""
        assert second == ""

    def test_cancel_tts_then_take(self) -> None:
        """Integration: cancel_tts sets latch, _take_speech_interrupted consumes it."""
        from app.api.voice.agent_bridge import _SPEECH_INTERRUPTED_NOTE

        bridge = make_bridge()
        bridge.cancel_tts()

        result = bridge._take_speech_interrupted()
        assert _SPEECH_INTERRUPTED_NOTE in result


class TestVoiceAgentBridgeHandleSttFinal:
    @pytest.mark.asyncio
    async def test_handle_stt_final_params_failed(self) -> None:
        """When _build_agent_params returns None, should speak fallback."""
        bridge = make_bridge()

        with (
            patch.object(bridge, "_build_agent_params", return_value=None),
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock) as mock_fb,
        ):
            await bridge.handle_stt_final("test query")

        mock_fb.assert_awaited_once()
        assert bridge._current_turn is None

    @pytest.mark.asyncio
    async def test_handle_stt_final_successful_turn(self) -> None:
        """Full successful turn: build params → agent stream → TTS."""
        bridge = make_bridge()

        mock_params = MagicMock()

        async def fake_stream(params: object, cancel_token: object, **kwargs: object) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "Hello."}

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream,
            ),
        ):
            await bridge.handle_stt_final("what is the weather")

        assert bridge._current_turn is None
        assert len(bridge._transcript) == 2
        assert bridge._transcript[0].role == "user"
        assert bridge._transcript[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_handle_stt_final_records_transcript(self) -> None:
        """Transcript should contain user + assistant entries."""
        bridge = make_bridge()

        with (
            patch.object(bridge, "_build_agent_params", return_value=None),
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock),
        ):
            await bridge.handle_stt_final("first")
            await bridge.handle_stt_final("second")

        assert len(bridge._transcript) == 2
        assert bridge._transcript[0].text == "first"
        assert bridge._transcript[1].text == "second"

    @pytest.mark.asyncio
    async def test_handle_stt_final_approval_prevents_fallback(self) -> None:
        """When agent stream yields approval_required, fallback must NOT fire."""
        bridge = make_bridge()
        mock_params = MagicMock()

        async def fake_stream_with_approval(
            params: object,
            cancel_token: object,
            **kwargs: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {
                "type": "approval_required",
                "data": {"action_type": "bash", "reason": "dangerous"},
            }

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock) as mock_handle,
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock) as mock_fb,
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream_with_approval,
            ),
        ):
            await bridge.handle_stt_final("delete the file")

        mock_handle.assert_awaited_once()
        mock_fb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_stt_final_tool_approval_request(self) -> None:
        """tool_approval_request event should be handled like approval_required."""
        bridge = make_bridge()
        mock_params = MagicMock()

        async def fake_stream_tool_approval(
            params: object,
            cancel_token: object,
            **kwargs: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {
                "type": "tool_approval_request",
                "data": {"actionRequests": [], "extensions": {}},
                "messageId": "msg-123",
            }

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock) as mock_handle,
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock) as mock_fb,
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream_tool_approval,
            ),
        ):
            await bridge.handle_stt_final("run the command")

        mock_handle.assert_awaited_once()
        mock_fb.assert_not_awaited()
