"""SMS (Twilio) channel — bidirectional text messaging via Twilio REST API.

Inbound: Twilio webhook POST (form-encoded) → validate signature → _emit_inbound
Outbound: text → Twilio Messages REST API → recipient phone

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.providers._twilio_utils::verify_twilio_signature (POS: Twilio signature verification)
- channels.core.credentials::credential_field, credential_spec (POS: Credential declarations)

[OUTPUT]
- SMSChannel: Twilio SMS bidirectional text Channel

[POS]
SMS channel provider. Sends/receives text messages via Twilio.
Inbound via webhook, outbound via REST API. Pure text (no markdown).
"""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.providers._twilio_utils import verify_twilio_signature
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

logger = logging.getLogger(__name__)

_MAX_SMS_LENGTH = 1600
_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
_SEND_TIMEOUT = 15.0


class SMSChannel(BaseChannel):
    """Twilio SMS channel.

    Inbound: business layer registers a webhook route that calls
    ``handle_inbound_webhook(url, params, signature, form)`` on this channel.

    Outbound: sends via Twilio Messages REST API with Basic Auth.
    Messages exceeding 1600 chars are split at natural boundaries.
    """

    name = "sms"
    channel_type = "sms"
    display_name = "SMS/Twilio"
    credential_spec = credential_spec(
        "smsCredentials",
        account_sid=credential_field("accountSid", "TWILIO_ACCOUNT_SID"),
        auth_token=credential_field("authToken", "TWILIO_AUTH_TOKEN"),
        phone_number=credential_field(
            "phoneNumber",
            "TWILIO_PHONE_NUMBER",
            help_text="E.164 format, e.g. +15551234567",
        ),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=False,
        max_text_length=_MAX_SMS_LENGTH,
    )
    render_style = RenderStyle(
        format="plaintext",
        use_emoji=False,
        max_text_length=_MAX_SMS_LENGTH,
        supports_code_fence=False,
        supports_links=False,
        supports_tables=False,
        tool_summary_display=ToolSummaryDisplay.OFF,
    )

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        *,
        phone_number: str = "",
    ) -> None:
        super().__init__()
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._phone_number = phone_number
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if not self._account_sid or not self._auth_token:
            logger.info("SMS: Twilio credentials not configured; channel idle")
            return
        self._client = httpx.AsyncClient(timeout=_SEND_TIMEOUT)
        await super().start()
        logger.info("SMSChannel started (from: %s)", _redact_phone(self._phone_number))

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().stop()

    # -- health & diagnostics ------------------------------------------------

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        ok = bool(self._account_sid and self._auth_token and self._phone_number)
        if ok:
            self.health.record_success()
        else:
            self.health.record_failure("SMS credentials incomplete")
        return ok

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        missing: list[str] = []
        if not self._account_sid:
            missing.append("account_sid")
        if not self._auth_token:
            missing.append("auth_token")
        if not self._phone_number:
            missing.append("phone_number")
        if missing:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"{', '.join(missing)} not configured.",
                    fix="Set Twilio credentials in Settings → Channels → SMS.",
                )
            )
            return issues
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="SMS channel is in ERROR state.",
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

    # -- inbound webhook handling --------------------------------------------

    def validate_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        """Validate X-Twilio-Signature on inbound webhook request."""
        return verify_twilio_signature(self._auth_token, url, params, signature)

    async def handle_inbound_webhook(
        self,
        url: str,
        params: dict[str, str],
        signature: str,
        form: dict[str, str],
    ) -> bool:
        """Process an inbound SMS webhook from Twilio.

        Args:
            url: Full webhook URL for signature verification.
            params: Flat form parameters for signature verification.
            signature: X-Twilio-Signature header value.
            form: Parsed form fields (From, To, Body, MessageSid).

        Returns:
            True if the message was accepted and dispatched.
        """
        if not self.validate_signature(url, params, signature):
            logger.warning("SMS: rejected inbound — invalid Twilio signature")
            return False

        from_number = form.get("From", "").strip()
        body = form.get("Body", "").strip()
        message_sid = form.get("MessageSid", "")

        if not from_number or not body:
            return False

        if from_number == self._phone_number:
            logger.debug("SMS: ignoring echo from own number %s", _redact_phone(from_number))
            return False

        msg = self._build_inbound(
            sender_id=from_number,
            content=body,
            chat_id=from_number,
            is_group=False,
            mentioned=True,
            media=(),
            metadata={"message_sid": message_sid, "channel": "sms"},
            message_id=message_sid,
        )
        await self._emit_inbound(msg)
        return True

    # -- outbound ------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send SMS to recipient via Twilio Messages REST API."""
        if not self._phone_number:
            logger.error("SMS: cannot send — phone_number not configured")
            return None

        to_number = msg.recipient_id
        if not to_number:
            return None

        chunks = render(msg, self.render_style)
        if not chunks:
            return None

        last_sid: str | None = None
        for chunk in chunks:
            sid = await self._send_sms(to_number, chunk)
            if sid:
                last_sid = sid
                self.health.record_success()
            else:
                self.health.record_failure(f"SMS send failed to {_redact_phone(to_number)}")
                break

        return last_sid

    async def _send_sms(self, to: str, body: str) -> str | None:
        """Send a single SMS via Twilio REST API. Returns message SID or None."""
        client = self._client or httpx.AsyncClient(timeout=_SEND_TIMEOUT)
        url = f"{_TWILIO_API_BASE}/{self._account_sid}/Messages.json"

        try:
            resp = await client.post(
                url,
                data={"From": self._phone_number, "To": to, "Body": body},
                auth=(self._account_sid, self._auth_token),
            )
            if resp.status_code >= 400:
                error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_body.get("message", resp.text[:200])
                logger.error("SMS: send failed (%d): %s", resp.status_code, error_msg)
                return None
            data = resp.json()
            return data.get("sid")
        except httpx.HTTPError as exc:
            logger.error("SMS: send error to %s: %s", _redact_phone(to), exc)
            return None

    # -- retry override for Twilio rate limits --------------------------------

    def should_retry(self, exc: BaseException) -> bool:
        """Retry on Twilio rate limit (HTTP 429) and server errors (5xx)."""
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        return super().should_retry(exc)

    # -- route registration --------------------------------------------------

    def register_routes(self, registrar: object) -> None:
        """Register POST /webhook for Twilio SMS inbound.

        Twilio sends form-encoded POST with fields: From, To, Body, MessageSid.
        We validate the X-Twilio-Signature header, parse the form, and dispatch.
        """
        from app.channels.protocols.route_registrar import (
            HttpMethod,
            RouteMetadata,
        )

        async def sms_webhook_handler(request: object) -> object:
            """Handle inbound SMS webhook from Twilio."""
            raw_body = await request.body()  # type: ignore[attr-defined]
            form = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8"), keep_blank_values=True))

            sig = ""
            headers = getattr(request, "headers", {})
            if hasattr(headers, "get"):
                sig = headers.get("x-twilio-signature", "")

            webhook_url = str(request.url) if hasattr(request, "url") else ""  # type: ignore[attr-defined]

            accepted = await self.handle_inbound_webhook(
                url=webhook_url,
                params=form,
                signature=sig,
                form=form,
            )

            class _TwiMLResponse:
                status_code = 200 if accepted else 403
                headers = {"content-type": "application/xml"}
                body = b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

            return _TwiMLResponse()

        registrar.add_route(  # type: ignore[attr-defined]
            method=HttpMethod.POST,
            path="webhook",
            handler=sms_webhook_handler,
            metadata=RouteMetadata(
                description="Receive inbound SMS from Twilio",
                requires_auth=False,
            ),
        )


def _redact_phone(phone: str) -> str:
    """Redact phone number for logging: +1555***4567."""
    if len(phone) <= 6:
        return "***"
    return phone[:4] + "***" + phone[-4:]
