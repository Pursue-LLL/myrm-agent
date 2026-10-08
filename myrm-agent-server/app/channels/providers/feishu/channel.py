"""Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging.

[INPUT]
- app.channels.types::ChannelCapabilities, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- app.channels.core.rate_limit::RateLimitConfig (POS: Rate limiting for inbound messages.)
- app.channels.protocols.route_registrar::HttpMethod, RouteMetadata (POS: Protocol layer for dynamic HTTP route registration. Enables channels to declare their own HTTP endpoints while maintaining framework independence. Business layer implements RouteRegistrar for a specific web framework (e.g. FastAPI via ``myrm-agent-harness[fastapi]``).)
- app.channels.security::SecurityLimits, (POS: Delegates SSRF logic to agent.security.guards.ssrf_guard (single source of truth). Adds media-specific concerns: max-length filenames, path traversal prevention, extension allowlisting.)
- app.channels.providers.feishu.inbound::FeishuInboundMixin (POS: webhook / websocket event handling)
- app.channels.providers.feishu.outbound::FeishuOutboundMixin (POS: message send, media upload, streaming cards)
- app.channels.core.base::BaseChannel, DedupMode (POS: Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. Supports outbound (send) and inbound (on_inbound callback) bidirectional communication. Providers may declare credential_spec and from_credentials for self-contained credential management.)
- app.channels.security.errors::WebhookResponseError (POS: Webhook error response layer. Provides RFC 7807 standardized error format, supporting machine-parsable and human-readable output without leaking sensitive data.)

[OUTPUT]
- FeishuChannel: Feishu/Lark Bot channel with dual transport (webhook / we...

[POS]
Feishu/Lark channel — dual transport (webhook / websocket) bidirectional messaging.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Self

from fastapi import Request

from app.channels.core.allow_policy import AllowPolicy, ChatPolicy
from app.channels.core.base import BaseChannel, DedupMode
from app.channels.core.credentials import credential_field, credential_spec, parse_bool
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    RenderStyle,
    ToolSummaryDisplay,
)

from .api import FeishuClient
from .inbound import FeishuInboundMixin
from .outbound import FeishuOutboundMixin
from .user_resolver import FeishuUserResolver

if TYPE_CHECKING:
    from .ws_transport import FeishuWSTransport

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4000


class FeishuChannel(FeishuOutboundMixin, FeishuInboundMixin, BaseChannel):
    """Feishu/Lark Bot channel with dual transport (webhook / websocket).

    Outbound always uses the lightweight httpx-based ``FeishuClient``.
    """

    name = "feishu"

    credential_spec = credential_spec(
        "feishuCredentials",
        app_id=credential_field("appId", "FEISHU_APP_ID"),
        app_secret=credential_field("appSecret", "FEISHU_APP_SECRET"),
        encrypt_key=credential_field("encryptKey", "FEISHU_ENCRYPT_KEY"),
        use_lark=credential_field("useLark", "FEISHU_USE_LARK", "false"),
        render_mode=credential_field("renderMode", "FEISHU_RENDER_MODE", "auto"),
        transport=credential_field("transport", "FEISHU_TRANSPORT", "websocket"),
        verification_token=credential_field("verificationToken", "FEISHU_VERIFICATION_TOKEN"),
        bot_policy=credential_field("botPolicy", "FEISHU_BOT_POLICY", "deny"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=True,
        quick_replies=True,
        select_menus=True,
        interactive_callback=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        transport = creds.get("transport", "websocket")
        if transport not in ("webhook", "websocket"):
            transport = "websocket"
        return cls(
            app_id=creds.get("app_id", ""),
            app_secret=creds.get("app_secret", ""),
            encrypt_key=creds.get("encrypt_key", ""),
            use_lark=parse_bool(creds.get("use_lark", "false")),
            render_mode=creds.get("render_mode", "auto"),
            transport=transport,
            verification_token=creds.get("verification_token", ""),
            bot_policy=creds.get("bot_policy", "deny"),
        )

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        encrypt_key: str = "",
        use_lark: bool = False,
        render_mode: str = "auto",
        transport: str = "websocket",
        verification_token: str = "",
        bot_policy: str = "deny",
    ) -> None:
        super().__init__()
        if not app_id or not app_id.strip():
            raise ValueError("app_id cannot be empty")
        if not app_secret or not app_secret.strip():
            raise ValueError("app_secret cannot be empty")
        self._app_id = app_id
        self._app_secret = app_secret
        self._encrypt_key = encrypt_key
        self._use_lark = use_lark
        self._render_mode = render_mode
        self._transport = transport
        self._verification_token = verification_token
        self._apply_bot_policy(bot_policy)
        self._client = FeishuClient(app_id, app_secret, use_lark=use_lark)
        self._user_resolver = FeishuUserResolver(self._client)
        self._ws_transport: FeishuWSTransport | None = None  # lazy import
        self._streaming_seq: dict[str, int] = {}
        self._streaming_card_ids: dict[str, str] = {}
        self._reaction_ids: dict[str, str] = {}  # message_id → reaction_id for removal

        self._dedup_mode = DedupMode.LRU
        self._dedup_capacity = 1000

    async def start(self) -> None:
        if not self._client.is_configured:
            logger.debug("Feishu credentials not configured; channel idle")
            return
        try:
            await self._client.ensure_token()
            await self._client.fetch_bot_info()
        except Exception as exc:
            logger.warning("FeishuChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._client.close()
            return

        if self._transport == "websocket":
            try:
                await self._start_ws_transport()
            except RuntimeError as exc:
                logger.error("FeishuChannel: WebSocket transport failed: %s", exc)
                self._status = ChannelStatus.ERROR
                return

        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        mode_label = "WebSocket" if self._transport == "websocket" else "Webhook"
        logger.info(
            "FeishuChannel: started (bot=%s, transport=%s)",
            self._client.bot_open_id,
            mode_label,
        )

    async def stop(self) -> None:
        for msg_id in list(self._streaming_card_ids):
            try:
                await self._streaming_finalize(msg_id, "")
            except Exception:
                logger.debug("Failed to finalize streaming for %s on stop", msg_id)
        if self._ws_transport:
            await self._ws_transport.stop()
            self._ws_transport = None
        self._reaction_ids.clear()
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._client.close()

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        ok = await self._client.verify_connectivity()
        if ok:
            self.health.record_success()
        else:
            self.health.record_failure()
        return ok

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate Feishu app_id and verification_token.

        Challenge requests (URL verification) skip validation since
        the Feishu platform sends them during webhook registration setup.
        """
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            parsed = {}

        if isinstance(parsed, dict) and "challenge" in parsed:
            return

        trace_id = getattr(request.state, "_webhook_trace_id", "")

        if "header" in parsed and isinstance(parsed["header"], dict):
            event_app_id = parsed["header"].get("app_id", "")
            if event_app_id and event_app_id != self._app_id:
                logger.warning(
                    "Feishu app_id mismatch: expected=%s, got=%s, trace_id=%s",
                    self._app_id,
                    event_app_id,
                    trace_id,
                )
                raise WebhookResponseError(
                    status_code=403,
                    error_type="app-id-mismatch",
                    title="App ID Mismatch",
                    detail=f"Expected app_id {self._app_id}, got {event_app_id}",
                    trace_id=trace_id,
                )

        if self._verification_token:
            body_token = parsed.get("token", "") if isinstance(parsed, dict) else ""
            if not hmac.compare_digest(str(body_token), self._verification_token):
                raise WebhookResponseError(
                    status_code=403,
                    error_type="signature-invalid",
                    title="Invalid Signature",
                    detail="Feishu verification token mismatch",
                    trace_id=trace_id,
                )

    def verify_webhook(self, body: bytes, timestamp: str, nonce: str, signature: str) -> bool:
        """Verify webhook signature: sha256(timestamp + nonce + encrypt_key + body)."""
        if not self._encrypt_key:
            return True
        prefix = (timestamp + nonce + self._encrypt_key).encode("utf-8")
        expected = hashlib.sha256(prefix + body).hexdigest()
        return hmac.compare_digest(expected, signature)

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._client.is_configured:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="App ID or App Secret not configured.",
                    fix="Set FEISHU_APP_ID and FEISHU_APP_SECRET, or configure in Settings → Channels → Feishu.",
                )
            )
            return issues
        if self._transport == "websocket":
            from .ws_transport import SDK_AVAILABLE

            if not SDK_AVAILABLE:
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.DEPENDENCY,
                        severity=IssueSeverity.ERROR,
                        message="lark-oapi not installed. Run: uv sync --extra channels-sdk",
                        fix="uv sync --extra channels-sdk",
                    )
                )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        return issues

    async def run_diagnostics(self) -> dict[str, object]:
        """Run comprehensive Feishu Doctor diagnostics and return structured JSON."""
        from .doctor import diagnose_feishu_channel

        report = await diagnose_feishu_channel(
            self._client,
            app_id=self._app_id,
            transport_mode=self._transport,
            webhook_url=self._webhook_url if hasattr(self, "_webhook_url") else None,
        )
        return {
            "app_id": report.app_id,
            "is_healthy": report.is_healthy,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "message": c.message,
                    "details": c.details,
                }
                for c in report.checks
            ],
            "recommendations": report.recommendations,
        }

    async def _start_ws_transport(self) -> None:
        """Initialize and start the WebSocket transport."""
        from .ws_transport import FeishuWSTransport

        self._ws_transport = FeishuWSTransport(
            self._app_id,
            self._app_secret,
            use_lark=self._use_lark,
            encrypt_key=self._encrypt_key,
            verification_token=self._verification_token,
        )
        await self._ws_transport.start(on_event=self.handle_webhook_event)

    # ── Private helpers ──────────────────────────────────────────

    _BOT_POLICY_MAP: dict[str, ChatPolicy] = {
        "deny": ChatPolicy.DENY,
        "mention_only": ChatPolicy.MENTION_ONLY,
        "allow": ChatPolicy.ALLOW,
    }

    def _apply_bot_policy(self, raw: str) -> None:
        """Parse bot_policy credential and update allow_policy if needed."""
        policy = self._BOT_POLICY_MAP.get(raw.strip().lower(), ChatPolicy.DENY)
        if policy != ChatPolicy.DENY:
            self.allow_policy = AllowPolicy(
                allowlist=self.allow_policy.allowlist,
                denylist=self.allow_policy.denylist,
                dm_policy=self.allow_policy.dm_policy,
                group_policy=self.allow_policy.group_policy,
                bot_policy=policy,
                chat_overrides=self.allow_policy.chat_overrides,
            )

    # ── CardKit streaming ─────────────────────────────────────────

    def register_routes(self, registrar: object) -> None:
        """Register custom HTTP routes for Feishu webhook.

        Registers POST /webhook endpoint for receiving Feishu event callbacks.
        Handles URL verification challenge, message events, @mention detection.

        Args:
            registrar: RouteRegistrar Protocol implementation (e.g., FastAPIRouteRegistrar)
        """
        from app.channels.core.rate_limit import (
            RateLimitConfig,
        )
        from app.channels.protocols.route_registrar import (
            HttpMethod,
            RouteMetadata,
        )
        from app.channels.security import (
            SecurityLimits,
            SecurityProtocols,
            WebhookResponseError,
            WebhookSecurityMiddleware,
        )

        middleware = WebhookSecurityMiddleware(
            limits=SecurityLimits(
                body_limit_pre_auth=10_000,
                body_limit_post_auth=10_000,
                read_timeout_seconds=5.0,
            ),
            protocols=SecurityProtocols(signature_verifier=self),
        )

        async def webhook_handler(request):
            """Handle Feishu webhook events."""
            import json

            try:
                ctx = await middleware.process_request(request, "feishu")

                if ctx.parsed_data is None:

                    class _ErrorResponse:
                        status_code = 400
                        headers = {}
                        body = b'{"error": "Invalid JSON"}'

                    return _ErrorResponse()

                result = await self.handle_webhook_event(ctx.parsed_data)
                if result is not None:

                    class _JsonResponse:
                        status_code = 200
                        headers = {}
                        body = json.dumps(result).encode("utf-8")

                    return _JsonResponse()

            except WebhookResponseError as e:

                class _WebhookErrorResponse:
                    status_code = e.status_code
                    headers = {}
                    body = json.dumps(e.to_dict()).encode("utf-8")

                return _WebhookErrorResponse()
            except Exception as e:
                logger.warning("Feishu webhook error: %s", e, exc_info=True)

                class _InternalErrorResponse:
                    status_code = 500
                    headers = {}
                    body = json.dumps({"ok": False, "error": "Internal error"}).encode("utf-8")

                return _InternalErrorResponse()

            class _SuccessResponse:
                status_code = 200
                headers = {}
                body = b'{"ok": true}'

            return _SuccessResponse()

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=webhook_handler,
            metadata=RouteMetadata(
                description="Receive Feishu event callback (URL verification, messages, @mentions)",
                requires_auth=False,
                rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            ),
        )
