"""Voice/Twilio channel — bidirectional voice calls via Twilio ConversationRelay.

Inbound: TwiML webhook → ConversationRelay WebSocket → STT → _emit_inbound
Outbound: text → ConversationRelay WebSocket → TTS → caller

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- VoiceCallChannel: Twilio ConversationRelay bidirectional voice Channel

[POS]
Voice/phone call channel. Twilio ConversationRelay WebSocket protocol.
Framework layer is WebSocket-library-agnostic — business layer injects receive/send functions.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from xml.sax.saxutils import quoteattr

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 10000
_CALL_TTL = 3600.0

SendFn = Callable[[str], Awaitable[None]]


class VoiceCallChannel(BaseChannel):
    """Voice channel using Twilio ConversationRelay.

    Framework-agnostic WebSocket design: handle_conversation_relay accepts
    a receive iterator and a send callable, decoupled from any WebSocket lib.
    """

    name = "voice"
    credential_spec = credential_spec(
        "twilioCredentials",
        account_sid=credential_field("accountSid", "TWILIO_ACCOUNT_SID"),
        auth_token=credential_field("authToken", "TWILIO_AUTH_TOKEN"),
        twiml_app_sid=credential_field("twimlAppSid", "TWILIO_TWIML_APP_SID"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(format="text", max_text_length=_MAX_TEXT_LENGTH)

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        *,
        twiml_app_sid: str = "",
        stt_provider: str = "google",
        tts_provider: str = "google",
        voice: str = "en-US-Standard-C",
        language: str = "en-US",
    ) -> None:
        super().__init__()
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._twiml_app_sid = twiml_app_sid
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._voice = voice
        self._language = language
        self._active_calls: dict[str, tuple[SendFn, float]] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if not self._account_sid or not self._auth_token:
            logger.info("Twilio credentials not configured; channel idle")
            return
        await super().start()
        logger.info("VoiceCallChannel started")

    async def stop(self) -> None:
        self._active_calls.clear()
        await super().stop()

    # -- health & diagnostics ------------------------------------------------

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        ok = bool(self._account_sid and self._auth_token)
        if ok:
            self.health.record_success()
        else:
            self.health.record_failure("Twilio credentials missing")
        return ok

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        missing: list[str] = []
        if not self._account_sid:
            missing.append("account_sid")
        if not self._auth_token:
            missing.append("auth_token")
        if missing:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"{', '.join(missing)} not configured.",
                    fix="Set Twilio account_sid and auth_token, or configure in Settings → Channels → Voice.",
                )
            )
            return issues
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Voice channel is in ERROR state.",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=self.health.last_error,
                )
            )
        return issues

    # -- webhook security ----------------------------------------------------

    def validate_twilio_signature(
        self,
        url: str,
        params: dict[str, str],
        signature: str,
    ) -> bool:
        """Validate Twilio webhook request signature (HMAC-SHA1).

        Delegates to shared utility that handles port-variant URL edge cases.
        """
        from app.channels.providers._twilio_utils import verify_twilio_signature

        return verify_twilio_signature(self._auth_token, url, params, signature)

    # -- outbound ------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        call_sid = msg.recipient_id
        call_entry = self._active_calls.get(call_sid)
        if not call_entry:
            logger.debug("VoiceCallChannel: no active call for %s", call_sid)
            return None

        send_fn, _ = call_entry
        if msg.content:
            chunks = render(msg, self.render_style)
            text = " ".join(chunks)
            payload = json.dumps({"type": "text", "token": text, "last": True})
            try:
                await send_fn(payload)
                self.health.record_success()
            except Exception:
                self.health.record_failure(f"send failed for call {call_sid}")
                logger.debug("VoiceCallChannel: send failed for %s", call_sid)
        return None

    # -- TwiML generation ----------------------------------------------------

    def generate_twiml(self, ws_url: str) -> str:
        """Generate TwiML response for incoming call setup."""
        safe = quoteattr
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"<Connect><ConversationRelay url={safe(ws_url)} "
            f"voice={safe(self._voice)} language={safe(self._language)} "
            f'speechModel="phone_call" '
            f"transcriptionProvider={safe(self._stt_provider)} "
            f"ttsProvider={safe(self._tts_provider)} "
            "/></Connect>"
            "</Response>"
        )

    # -- ConversationRelay WebSocket handler ---------------------------------

    async def handle_conversation_relay(
        self,
        receive: AsyncIterator[str | bytes],
        send_fn: SendFn,
        call_sid: str,
    ) -> None:
        """Handle a ConversationRelay WebSocket session for one call.

        Args:
            receive: async iterator yielding JSON messages from Twilio.
            send_fn: coroutine to send a JSON string back to Twilio.
            call_sid: unique Twilio call SID.
        """
        self._register_call(call_sid, send_fn)
        try:
            async for raw in receive:
                text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue

                if not isinstance(data, dict):
                    continue

                event_type = data.get("type", "")
                if not isinstance(event_type, str):
                    continue

                if event_type == "prompt":
                    await self._handle_prompt(data, call_sid)
                elif event_type == "dtmf":
                    await self._handle_dtmf(data, call_sid)
                elif event_type == "interrupt":
                    logger.debug("VoiceCallChannel: caller interrupted (call=%s)", call_sid)
                elif event_type == "setup":
                    logger.info(
                        "VoiceCallChannel: call setup (sid=%s, from=%s)",
                        call_sid,
                        data.get("from", ""),
                    )
        except Exception as exc:
            self.health.record_failure(f"WebSocket error: {exc}")
            logger.warning("VoiceCallChannel: WebSocket error for %s: %s", call_sid, exc)
        finally:
            self._active_calls.pop(call_sid, None)

    # -- active call management ----------------------------------------------

    def _register_call(self, call_sid: str, send_fn: SendFn) -> None:
        """Register a new call and evict stale entries beyond TTL."""
        now = time.monotonic()
        self._active_calls[call_sid] = (send_fn, now)
        stale = [sid for sid, (_, ts) in self._active_calls.items() if now - ts > _CALL_TTL and sid != call_sid]
        for sid in stale:
            self._active_calls.pop(sid, None)
            logger.info("VoiceCallChannel: evicted stale call %s", sid)

    @property
    def active_call_count(self) -> int:
        return len(self._active_calls)

    # -- inbound event handlers ----------------------------------------------

    async def _handle_prompt(self, data: dict[str, object], call_sid: str) -> None:
        """Process STT transcription from ConversationRelay."""
        raw_text = data.get("voicePrompt", "")
        voice_text = str(raw_text) if raw_text else ""
        if not voice_text.strip():
            return

        raw_from = data.get("from", call_sid)
        sender = str(raw_from) if raw_from else call_sid

        raw_handoff = data.get("handoffData")
        msg_id = ""
        if isinstance(raw_handoff, dict):
            raw_id = raw_handoff.get("id", "")
            msg_id = str(raw_id) if raw_id else ""

        msg = self._build_inbound(
            sender_id=sender,
            content=voice_text.strip(),
            chat_id=call_sid,
            is_group=False,
            mentioned=True,
            media=(),
            metadata={"call_sid": call_sid},
            message_id=msg_id,
        )
        await self._emit_inbound(msg)

    async def _handle_dtmf(self, data: dict[str, object], call_sid: str) -> None:
        """Report DTMF digit as inbound message so Agent can respond."""
        raw_digit = data.get("digit", "")
        digit = str(raw_digit) if raw_digit else ""
        if not digit:
            return

        msg = self._build_inbound(
            sender_id=call_sid,
            content=f"[DTMF:{digit}]",
            chat_id=call_sid,
            is_group=False,
            mentioned=True,
            media=(),
            metadata={"call_sid": call_sid, "dtmf": digit},
            message_id="",
        )
        await self._emit_inbound(msg)
