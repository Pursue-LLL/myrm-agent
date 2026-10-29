"""Voice agent bridge: approval requests and the loop guard pause.

Covers:
  - VoiceAgentBridge._handle_approval_required: TTS hint + WS forwarding
  - VoiceAgentBridge: approval events in _consume_agent_stream
"""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.support.harness_pause_event import harness_pause_event
from tests.support.voice_bridge import FakeVoiceConfig, make_bridge


class TestHandleApprovalRequired:
    @pytest.mark.asyncio
    async def test_tts_hint_zh(self) -> None:
        """Chinese language config should use Chinese TTS hint."""
        bridge = make_bridge()
        bridge._voice_config = FakeVoiceConfig(stt_language="zh-CN")  # type: ignore[assignment]
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
        bridge = make_bridge()
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
    @pytest.mark.parametrize(
        ("stt_language", "stop_wording"),
        [("zh-CN", "连续失败"), ("en", "kept failing")],
    )
    async def test_loop_guard_pause_is_spoken_as_a_stop_not_as_a_confirmation(self, stt_language: str, stop_wording: str) -> None:
        """A loop guard pause waits on no answer: the hint says the step was stopped, never to confirm on screen."""
        bridge = make_bridge()
        bridge._voice_config = FakeVoiceConfig(stt_language=stt_language)  # type: ignore[assignment]
        bridge._current_turn = "turn-1"

        with patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_tts:
            await bridge._handle_approval_required(harness_pause_event(), "turn-1")

        mock_tts.assert_awaited_once()
        hint_text = mock_tts.call_args[0][0]
        assert stop_wording in hint_text
        assert "屏幕" not in hint_text
        assert "confirm" not in hint_text.lower()

    @pytest.mark.asyncio
    async def test_loop_guard_pause_event_still_reaches_the_client(self) -> None:
        """The client gets the pause event unchanged; only the spoken hint differs from an approval's."""
        bridge = make_bridge()
        bridge._current_turn = "turn-1"
        pause = harness_pause_event()
        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(pause, "turn-1")

        assert sent_payloads == [
            {"type": "approval_required", "turn_id": "turn-1", "data": pause["data"], "messageId": pause["messageId"]}
        ]

    @pytest.mark.asyncio
    async def test_loop_guard_pauses_of_parallel_tool_calls_are_spoken_once_per_turn(self) -> None:
        """Parallel tool calls can stop together; the stop is said once, every pause event still reaches the client."""
        bridge = make_bridge()
        sent_payloads: list[dict[str, object]] = []

        async def capture_send(data: dict[str, object]) -> None:
            sent_payloads.append(data)

        with (
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_tts,
            patch.object(bridge, "_send_json", side_effect=capture_send),
        ):
            await bridge._handle_approval_required(harness_pause_event("a_tool", "call-a"), "turn-1")
            await bridge._handle_approval_required(harness_pause_event("b_tool", "call-b"), "turn-1")
            await bridge._handle_approval_required(harness_pause_event("a_tool", "call-c"), "turn-2")

        assert [call.args[1] for call in mock_tts.await_args_list] == ["turn-1", "turn-2"]
        assert len(sent_payloads) == 3

    @pytest.mark.asyncio
    async def test_every_approval_of_a_turn_still_gets_its_confirmation_hint(self) -> None:
        bridge = make_bridge()
        approval: dict[str, object] = {"type": "approval_required", "data": {"action_type": "bash"}}

        with patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_tts:
            await bridge._handle_approval_required(approval, "turn-1")
            await bridge._handle_approval_required(approval, "turn-1")

        assert mock_tts.await_count == 2

    @pytest.mark.asyncio
    async def test_ws_payload_structure(self) -> None:
        """WS payload should contain type, turn_id, and data from event."""
        bridge = make_bridge()
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
        bridge = make_bridge()
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
        bridge = make_bridge()
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
        bridge = make_bridge()
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
        bridge = make_bridge()
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
        bridge = make_bridge()
        bridge._current_turn = "turn-1"
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
            **kwargs: object,
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
        bridge = make_bridge()
        bridge._current_turn = "turn-1"
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
            **kwargs: object,
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
        bridge = make_bridge()
        mock_params = MagicMock()

        async def fake_stream(
            params: object,
            cancel_token: object,
            **kwargs: object,
        ) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "Running command."}
            yield {"type": "approval_required", "data": {}}

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock),
            patch.object(bridge, "_handle_approval_required", new_callable=AsyncMock),
            patch.object(bridge, "_speak_fallback", new_callable=AsyncMock),
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
