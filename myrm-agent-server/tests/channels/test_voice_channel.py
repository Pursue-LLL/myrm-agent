"""VoiceCallChannel tests — lifecycle, health, WebSocket relay, signature, diagnostics."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.voice_channel import (
    _CALL_TTL,
    VoiceCallChannel,
)
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
)

from .channel_test_base import ChannelTestBase

_SID = "AC_test_sid"
_TOKEN = "test_auth_token"


# ---------------------------------------------------------------------------
# Contract compliance (ChannelTestBase)
# ---------------------------------------------------------------------------


class TestVoiceChannelBase(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return VoiceCallChannel(account_sid=_SID, auth_token=_TOKEN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ch(**kwargs: object) -> VoiceCallChannel:
    defaults: dict[str, object] = {"account_sid": _SID, "auth_token": _TOKEN}
    defaults.update(kwargs)
    return VoiceCallChannel(**defaults)  # type: ignore[arg-type]


def _outbound(recipient: str = "CA123", content: str = "Hello") -> OutboundMessage:
    return OutboundMessage(
        channel="voice",
        recipient_id=recipient,
        content=content,
        user_id="system",
    )


async def _ws_stream(messages: list[str]) -> AsyncIterator[str]:
    for m in messages:
        yield m


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        ch = _ch()
        await ch.start()
        assert ch.status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_calls_super(self) -> None:
        """super().start() sets RUNNING + health.record_success."""
        ch = _ch()
        await ch.start()
        assert ch.health.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_start_no_creds_stays_idle(self) -> None:
        ch = VoiceCallChannel(account_sid="", auth_token="")
        await ch.start()
        assert ch.status == ChannelStatus.IDLE

    @pytest.mark.asyncio
    async def test_stop_clears_active_calls(self) -> None:
        ch = _ch()
        await ch.start()
        ch._active_calls["CA_fake"] = (AsyncMock(), time.monotonic())
        await ch.stop()
        assert ch.status == ChannelStatus.STOPPED
        assert len(ch._active_calls) == 0


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy_when_running(self) -> None:
        ch = _ch()
        await ch.start()
        assert await ch.health_check() is True
        assert ch.health.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_unhealthy_when_idle(self) -> None:
        ch = _ch()
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_stopped(self) -> None:
        ch = _ch()
        await ch.start()
        await ch.stop()
        assert await ch.health_check() is False


# ---------------------------------------------------------------------------
# Diagnostics (collect_issues)
# ---------------------------------------------------------------------------


class TestCollectIssues:
    def test_no_issues_when_configured(self) -> None:
        ch = _ch()
        assert ch.collect_issues() == []

    def test_missing_account_sid(self) -> None:
        ch = VoiceCallChannel(account_sid="", auth_token=_TOKEN)
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert issues[0].kind == IssueKind.CONFIG
        assert "account_sid" in issues[0].message
        assert issues[0].fix != ""

    def test_missing_auth_token(self) -> None:
        ch = VoiceCallChannel(account_sid=_SID, auth_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "auth_token" in issues[0].message

    def test_missing_both(self) -> None:
        ch = VoiceCallChannel(account_sid="", auth_token="")
        issues = ch.collect_issues()
        assert len(issues) == 1
        assert "account_sid" in issues[0].message
        assert "auth_token" in issues[0].message

    def test_error_state_issue(self) -> None:
        ch = _ch()
        ch._status = ChannelStatus.ERROR
        issues = ch.collect_issues()
        assert any(i.kind == IssueKind.RUNTIME and i.severity == IssueSeverity.ERROR for i in issues)

    def test_health_last_error_issue(self) -> None:
        ch = _ch()
        ch._status = ChannelStatus.RUNNING
        ch.health.record_failure("test error")
        issues = ch.collect_issues()
        assert any(i.message == "test error" for i in issues)


# ---------------------------------------------------------------------------
# Twilio Signature Validation
# ---------------------------------------------------------------------------


class TestSignatureValidation:
    @staticmethod
    def _twilio_sig(token: str, url: str, params: dict[str, str]) -> str:
        """Compute Twilio-compatible HMAC-SHA1 signature (key+value concatenation, no delimiters)."""
        data_to_sign = url + "".join(k + v for k, v in sorted(params.items()))
        computed = hmac.new(
            token.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(computed).decode("ascii")

    def test_valid_signature(self) -> None:
        ch = _ch()
        url = "https://example.com/webhook"
        params = {"CallSid": "CA123", "From": "+1234567890"}
        sig = self._twilio_sig(_TOKEN, url, params)
        assert ch.validate_twilio_signature(url, params, sig) is True

    def test_invalid_signature(self) -> None:
        ch = _ch()
        assert ch.validate_twilio_signature("https://x.com/w", {}, "wrong") is False

    def test_empty_auth_token(self) -> None:
        ch = VoiceCallChannel(account_sid=_SID, auth_token="")
        assert ch.validate_twilio_signature("https://x.com/w", {}, "sig") is False

    def test_empty_params(self) -> None:
        ch = _ch()
        url = "https://example.com/w"
        sig = self._twilio_sig(_TOKEN, url, {})
        assert ch.validate_twilio_signature(url, {}, sig) is True

    def test_params_with_special_chars(self) -> None:
        """Twilio concatenates key+value without URL encoding or delimiters."""
        ch = _ch()
        url = "https://example.com/webhook"
        params = {"From": "+1 555 0100", "To": "+1 555 0200"}
        sig = self._twilio_sig(_TOKEN, url, params)
        assert ch.validate_twilio_signature(url, params, sig) is True


# ---------------------------------------------------------------------------
# TwiML Generation
# ---------------------------------------------------------------------------


class TestTwiML:
    def test_generate_twiml(self) -> None:
        ch = _ch()
        twiml = ch.generate_twiml("wss://relay.example.com/ws")
        assert "ConversationRelay" in twiml
        assert "wss://relay.example.com/ws" in twiml
        assert 'voice="en-US-Standard-C"' in twiml
        assert 'language="en-US"' in twiml

    def test_custom_voice_and_language(self) -> None:
        ch = VoiceCallChannel(
            account_sid=_SID,
            auth_token=_TOKEN,
            voice="ja-JP-Neural2-B",
            language="ja-JP",
        )
        twiml = ch.generate_twiml("wss://x.com/ws")
        assert 'voice="ja-JP-Neural2-B"' in twiml
        assert 'language="ja-JP"' in twiml

    def test_url_quoting(self) -> None:
        ch = _ch()
        twiml = ch.generate_twiml("wss://x.com/ws?a=1&b=2")
        assert "&amp;" in twiml


# ---------------------------------------------------------------------------
# Outbound (send)
# ---------------------------------------------------------------------------


class TestSend:
    @pytest.mark.asyncio
    async def test_send_to_active_call(self) -> None:
        ch = _ch()
        mock_send = AsyncMock()
        ch._active_calls["CA123"] = (mock_send, time.monotonic())
        await ch.send(_outbound("CA123", "Hi"))
        mock_send.assert_called_once()
        payload = json.loads(mock_send.call_args[0][0])
        assert payload["type"] == "text"
        assert payload["last"] is True

    @pytest.mark.asyncio
    async def test_send_no_active_call(self) -> None:
        ch = _ch()
        result = await ch.send(_outbound("CA_missing"))
        assert result is None

    @pytest.mark.asyncio
    async def test_send_empty_content(self) -> None:
        ch = _ch()
        mock_send = AsyncMock()
        ch._active_calls["CA123"] = (mock_send, time.monotonic())
        await ch.send(_outbound("CA123", ""))
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_failure_records_health(self) -> None:
        ch = _ch()
        mock_send = AsyncMock(side_effect=ConnectionError("broken"))
        ch._active_calls["CA123"] = (mock_send, time.monotonic())
        await ch.send(_outbound("CA123", "test"))
        assert ch.health.consecutive_failures > 0

    @pytest.mark.asyncio
    async def test_send_success_records_health(self) -> None:
        ch = _ch()
        mock_send = AsyncMock()
        ch._active_calls["CA123"] = (mock_send, time.monotonic())
        ch.health.record_failure("previous")
        await ch.send(_outbound("CA123", "test"))
        assert ch.health.consecutive_failures == 0


# ---------------------------------------------------------------------------
# ConversationRelay WebSocket handler
# ---------------------------------------------------------------------------


class TestHandleConversationRelay:
    @pytest.mark.asyncio
    async def test_prompt_event(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = [json.dumps({"type": "prompt", "voicePrompt": "Hello world", "from": "+1555"})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA001")
        assert len(received) == 1
        assert received[0].content == "Hello world"
        assert received[0].chat_id == "CA001"

    @pytest.mark.asyncio
    async def test_dtmf_event(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = [json.dumps({"type": "dtmf", "digit": "5"})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA002")
        assert len(received) == 1
        assert "[DTMF:5]" in received[0].content

    @pytest.mark.asyncio
    async def test_empty_prompt_ignored(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = [json.dumps({"type": "prompt", "voicePrompt": "  "})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA003")
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_empty_dtmf_ignored(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = [json.dumps({"type": "dtmf", "digit": ""})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA004")
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_setup_event_logged(self) -> None:
        ch = _ch()
        ch.set_inbound_handler(AsyncMock())
        msgs = [json.dumps({"type": "setup", "from": "+1999"})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA005")

    @pytest.mark.asyncio
    async def test_interrupt_event(self) -> None:
        ch = _ch()
        ch.set_inbound_handler(AsyncMock())
        msgs = [json.dumps({"type": "interrupt"})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA006")

    @pytest.mark.asyncio
    async def test_invalid_json_skipped(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = ["not json", json.dumps({"type": "prompt", "voicePrompt": "valid"})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA007")
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_non_dict_json_skipped(self) -> None:
        ch = _ch()
        ch.set_inbound_handler(AsyncMock())
        msgs = [json.dumps([1, 2, 3])]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA008")

    @pytest.mark.asyncio
    async def test_non_string_type_skipped(self) -> None:
        ch = _ch()
        ch.set_inbound_handler(AsyncMock())
        msgs = [json.dumps({"type": 42})]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA009")

    @pytest.mark.asyncio
    async def test_call_removed_after_ws_completes(self) -> None:
        ch = _ch()
        ch.set_inbound_handler(AsyncMock())
        await ch.handle_conversation_relay(_ws_stream([]), AsyncMock(), "CA010")
        assert "CA010" not in ch._active_calls

    @pytest.mark.asyncio
    async def test_ws_error_records_health(self) -> None:
        ch = _ch()

        async def _error_stream() -> AsyncIterator[str]:
            raise RuntimeError("ws broke")
            yield ""

        await ch.handle_conversation_relay(_error_stream(), AsyncMock(), "CA011")
        assert ch.health.consecutive_failures > 0

    @pytest.mark.asyncio
    async def test_bytes_input_decoded(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        raw = json.dumps({"type": "prompt", "voicePrompt": "bytes test"}).encode()

        async def _byte_stream() -> AsyncIterator[bytes]:
            yield raw

        await ch.handle_conversation_relay(_byte_stream(), AsyncMock(), "CA012")
        assert len(received) == 1
        assert received[0].content == "bytes test"

    @pytest.mark.asyncio
    async def test_handoff_data_extracts_id(self) -> None:
        ch = _ch()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(AsyncMock(side_effect=lambda msg: received.append(msg)))
        await ch.start()

        msgs = [
            json.dumps(
                {
                    "type": "prompt",
                    "voicePrompt": "hi",
                    "handoffData": {"id": "msg_123"},
                }
            )
        ]
        await ch.handle_conversation_relay(_ws_stream(msgs), AsyncMock(), "CA013")
        assert received[0].message_id == "msg_123"


# ---------------------------------------------------------------------------
# Active Call Management
# ---------------------------------------------------------------------------


class TestActiveCallManagement:
    def test_register_call(self) -> None:
        ch = _ch()
        ch._register_call("CA100", AsyncMock())
        assert ch.active_call_count == 1

    def test_stale_call_eviction(self) -> None:
        ch = _ch()
        stale_ts = time.monotonic() - _CALL_TTL - 100
        ch._active_calls["CA_old"] = (AsyncMock(), stale_ts)
        ch._register_call("CA_new", AsyncMock())
        assert "CA_old" not in ch._active_calls
        assert "CA_new" in ch._active_calls

    def test_current_call_not_evicted(self) -> None:
        ch = _ch()
        ch._register_call("CA200", AsyncMock())
        assert "CA200" in ch._active_calls

    def test_active_call_count_property(self) -> None:
        ch = _ch()
        assert ch.active_call_count == 0
        ch._active_calls["CA1"] = (AsyncMock(), time.monotonic())
        ch._active_calls["CA2"] = (AsyncMock(), time.monotonic())
        assert ch.active_call_count == 2


# ---------------------------------------------------------------------------
# Capabilities & Attributes
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_name_is_voice(self) -> None:
        ch = _ch()
        assert ch.name == "voice"

    def test_text_capability(self) -> None:
        ch = _ch()
        assert ch.capabilities.text is True

    def test_max_text_length(self) -> None:
        ch = _ch()
        assert ch.capabilities.max_text_length == 10000

    def test_constructor_defaults(self) -> None:
        ch = _ch()
        assert ch._stt_provider == "google"
        assert ch._tts_provider == "google"
        assert ch._voice == "en-US-Standard-C"
        assert ch._language == "en-US"

    def test_custom_providers(self) -> None:
        ch = VoiceCallChannel(
            account_sid=_SID,
            auth_token=_TOKEN,
            stt_provider="deepgram",
            tts_provider="elevenlabs",
        )
        assert ch._stt_provider == "deepgram"
        assert ch._tts_provider == "elevenlabs"
