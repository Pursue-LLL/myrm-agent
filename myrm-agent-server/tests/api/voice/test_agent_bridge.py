"""Unit tests for voice agent bridge (agent_bridge.py).

Covers:
  - _extract_speakable_segments: sentence splitting
  - _log_turn_latency: latency logging format
  - VoiceAgentBridge: cancel_tts, _cancel_current_turn, _send_json error handling
  - VoiceAgentBridge.handle_stt_final: turn lifecycle with mocked dependencies
  - VoiceAgentBridge._handle_approval_required: TTS hint + WS forwarding
  - VoiceAgentBridge: approval events in _consume_agent_stream
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.voice.agent_bridge import (
    VoiceAgentBridge,
    _extract_speakable_segments,
    _log_turn_latency,
)

# ── _extract_speakable_segments tests ──────────────────────────────────


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


# ── VoiceAgentBridge unit tests ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _FakeVoiceConfig:
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


def _make_bridge(ws: AsyncMock | None = None) -> VoiceAgentBridge:
    mock_ws = ws or AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.send_bytes = AsyncMock()
    return VoiceAgentBridge(
        _ws=mock_ws,
        _voice_config=_FakeVoiceConfig(),  # type: ignore[arg-type]
        _agent_id="test-agent",
        _chat_id="test-chat",
    )


class TestVoiceAgentBridgeSendJson:
    @pytest.mark.asyncio
    async def test_send_json_success(self) -> None:
        bridge = _make_bridge()
        await bridge._send_json({"type": "test"})
        bridge._ws.send_text.assert_awaited_once()
        sent = json.loads(bridge._ws.send_text.call_args[0][0])
        assert sent["type"] == "test"

    @pytest.mark.asyncio
    async def test_send_json_error_sets_closed(self) -> None:
        bridge = _make_bridge()
        bridge._ws.send_text.side_effect = RuntimeError("WS closed")
        await bridge._send_json({"type": "test"})
        assert bridge._closed is True

    @pytest.mark.asyncio
    async def test_send_json_skips_when_closed(self) -> None:
        bridge = _make_bridge()
        bridge._closed = True
        await bridge._send_json({"type": "test"})
        bridge._ws.send_text.assert_not_awaited()


class TestVoiceAgentBridgeCancelTts:
    def test_cancel_tts_sets_event(self) -> None:
        bridge = _make_bridge()
        assert not bridge._tts_cancel_event.is_set()
        bridge.cancel_tts()
        assert bridge._tts_cancel_event.is_set()

    def test_cancel_current_turn(self) -> None:
        bridge = _make_bridge()
        from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

        token = CancellationToken()
        bridge._cancel_token = token
        bridge._current_turn = "turn-1"

        bridge._cancel_current_turn()

        assert token.is_cancelled
        assert bridge._current_turn is None
        assert bridge._cancel_token is None
        assert bridge._tts_cancel_event.is_set()


class TestVoiceAgentBridgeHandleSttFinal:
    @pytest.mark.asyncio
    async def test_handle_stt_final_params_failed(self) -> None:
        """When _build_agent_params returns None, should speak fallback."""
        bridge = _make_bridge()

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
        bridge = _make_bridge()

        mock_params = MagicMock()

        async def fake_stream(params: object, cancel_token: object) -> AsyncIterator[dict[str, object]]:
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
        bridge = _make_bridge()

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
        bridge = _make_bridge()
        mock_params = MagicMock()

        async def fake_stream_with_approval(
            params: object,
            cancel_token: object,
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
        bridge = _make_bridge()
        mock_params = MagicMock()

        async def fake_stream_tool_approval(
            params: object,
            cancel_token: object,
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


class TestHandleApprovalRequired:
    @pytest.mark.asyncio
    async def test_tts_hint_zh(self) -> None:
        """Chinese language config should use Chinese TTS hint."""
        bridge = _make_bridge()
        bridge._voice_config = _FakeVoiceConfig(stt_language="zh-CN")  # type: ignore[assignment]
        bridge._current_turn = "turn-1"

        with patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_tts:
            await bridge._handle_approval_required(
                {"type": "approval_required", "data": {"action_type": "bash"}},
                "turn-1",
            )

        mock_tts.assert_awaited_once()
        hint_text = mock_tts.call_args[0][0]
        assert "屏幕" in hint_text or "确认" in hint_text

    @pytest.mark.asyncio
    async def test_tts_hint_en(self) -> None:
        """English language config should use English TTS hint."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        with patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_tts:
            await bridge._handle_approval_required(
                {"type": "approval_required", "data": {}},
                "turn-1",
            )

        mock_tts.assert_awaited_once()
        hint_text = mock_tts.call_args[0][0]
        assert "confirmation" in hint_text.lower() or "screen" in hint_text.lower()

    @pytest.mark.asyncio
    async def test_ws_payload_structure(self) -> None:
        """WS payload should contain type, turn_id, and data from event."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        sent_payloads: list[dict[str, object]] = []
        original_send = bridge._send_json

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)
            await original_send(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(
                {
                    "type": "tool_approval_request",
                    "data": {"actionRequests": [{"action": "bash"}]},
                    "messageId": "msg-456",
                },
                "turn-1",
            )

        assert len(sent_payloads) == 1
        payload = sent_payloads[0]
        assert payload["type"] == "tool_approval_request"
        assert payload["turn_id"] == "turn-1"
        assert payload["messageId"] == "msg-456"
        assert isinstance(payload["data"], dict)

    @pytest.mark.asyncio
    async def test_ws_payload_preserves_event_type(self) -> None:
        """Original event type should be preserved in WS payload."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(
                {"type": "approval_required", "data": {"action_type": "email"}},
                "turn-1",
            )

        assert sent_payloads[0]["type"] == "approval_required"

    @pytest.mark.asyncio
    async def test_no_message_id_omitted(self) -> None:
        """When event has no messageId, WS payload should not include it."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(
                {"type": "approval_required", "data": {}},
                "turn-1",
            )

        assert "messageId" not in sent_payloads[0]

    @pytest.mark.asyncio
    async def test_non_dict_data_excluded(self) -> None:
        """When event data is not a dict, WS payload should omit data field."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(
                {"type": "approval_required", "data": "not-a-dict"},
                "turn-1",
            )

        assert "data" not in sent_payloads[0]

    @pytest.mark.asyncio
    async def test_default_event_type(self) -> None:
        """When event has no 'type' key, default to 'approval_required'."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"

        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(
                {"data": {"action_type": "bash"}},
                "turn-1",
            )

        assert sent_payloads[0]["type"] == "approval_required"


class TestConsumeAgentStreamApproval:
    """Tests for _consume_agent_stream approval event handling."""

    @pytest.mark.asyncio
    async def test_message_then_approval(self) -> None:
        """Agent sends text first, then approval: both should be handled."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "I need to run a command."}
            yield {"type": "approval_required", "data": {"action_type": "bash"}}

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock) as mock_handle,
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream,
            ),
        ):
            full_text, has_approval = await bridge._consume_agent_stream(
                mock_params,
                MagicMock(),
                "turn-1",
            )

        assert full_text == "I need to run a command."
        assert has_approval is True
        mock_handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_approval_events(self) -> None:
        """Multiple approval events should all be handled, has_approval stays True."""
        bridge = _make_bridge()
        bridge._current_turn = "turn-1"
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {"type": "approval_required", "data": {"action_type": "bash"}}
            yield {"type": "tool_approval_request", "data": {"actionRequests": []}}

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock) as mock_handle,
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream,
            ),
        ):
            full_text, has_approval = await bridge._consume_agent_stream(
                mock_params,
                MagicMock(),
                "turn-1",
            )

        assert full_text == ""
        assert has_approval is True
        assert mock_handle.await_count == 2

    @pytest.mark.asyncio
    async def test_approval_with_text_records_transcript(self) -> None:
        """When both text and approval exist, text should be in transcript."""
        bridge = _make_bridge()
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "Running command."}
            yield {"type": "approval_required", "data": {}}

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock),
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock) as mock_fb,
            patch(
                "app.services.agent.streaming.ai_agent_service_stream",
                side_effect=fake_stream,
            ),
        ):
            await bridge.handle_stt_final("run the test")

        assert len(bridge._transcript) == 2
        assert bridge._transcript[0].role == "user"
        assert bridge._transcript[1].role == "assistant"
        assert bridge._transcript[1].text == "Running command."


class TestBuildAgentParamsWebFetchGate:
    """Voice bridge must honor Agent Security net_fetch like Web/Channel."""

    @pytest.mark.asyncio
    async def test_enable_web_fetch_false_when_profile_omits_net_fetch(self) -> None:
        from app.core.types import ModelConfig
        from app.services.agent.profile_resolver import ResolvedAgentProfile

        bridge = _make_bridge()
        profile = ResolvedAgentProfile(
            agent_id="restricted-agent",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("file_read",),
            security_overrides={"capabilities": ["file_read"]},
        )
        mock_configs = MagicMock()
        mock_configs.model_cfg = ModelConfig(model="test/model", api_key="test-key")
        mock_configs.providers_dict = {}
        mock_configs.retrieval_dict = {}
        mock_configs.mcp_dict = {}
        mock_configs.search_cfg = None
        mock_configs.personal_settings_dict = {}

        with (
            patch("app.api.voice.agent_bridge._ensure_model_rebuild"),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.profile_resolver.get_agent_profile_resolver",
            ) as mock_get_resolver,
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_fallback_model_configs",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_retrieval_models",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_mcp_configs",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_user_instructions",
                return_value="",
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=profile)
            mock_get_resolver.return_value = mock_resolver

            params = await bridge._build_agent_params("read https://example.com")

        assert params is not None
        assert params.enable_web_fetch is False
        assert params.agent_security_raw == {"capabilities": ["file_read"]}

    @pytest.mark.asyncio
    async def test_enable_web_fetch_true_when_no_security_overrides(self) -> None:
        from app.core.types import ModelConfig
        from app.services.agent.profile_resolver import ResolvedAgentProfile

        bridge = _make_bridge()
        profile = ResolvedAgentProfile(
            agent_id="default-agent",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("file_read", "web_search"),
        )
        mock_configs = MagicMock()
        mock_configs.model_cfg = ModelConfig(model="test/model", api_key="test-key")
        mock_configs.providers_dict = {}
        mock_configs.retrieval_dict = {}
        mock_configs.mcp_dict = {}
        mock_configs.search_cfg = None
        mock_configs.personal_settings_dict = {}

        with (
            patch("app.api.voice.agent_bridge._ensure_model_rebuild"),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.profile_resolver.get_agent_profile_resolver",
            ) as mock_get_resolver,
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_fallback_model_configs",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_retrieval_models",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_mcp_configs",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_user_instructions",
                return_value="",
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=profile)
            mock_get_resolver.return_value = mock_resolver

            params = await bridge._build_agent_params("hello")

        assert params is not None
        assert params.enable_web_fetch is True
        assert params.agent_security_raw is None
