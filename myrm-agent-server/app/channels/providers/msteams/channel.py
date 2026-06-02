"""Microsoft Teams channel — bidirectional messaging via Bot Framework.

Inbound: HTTP webhook (Bot Framework activity) → _parse_activity → _emit_inbound
  - Text, file attachments, mentions, quote/reply context
  - 1:1 and group chat/team channel support
  - Adaptive Card invoke callbacks (interactive components)
Outbound: Bot Framework connector API (text/adaptive card/file attachment)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.providers.msteams.api::BotFrameworkApi (POS: HTTP/OAuth layer)
- channels.providers.msteams.helpers (POS: HTML parsing, message encoding, Adaptive Card building)
- channels.providers.msteams.auth::BotFrameworkJwtVerifier (POS: JWT verification)

[OUTPUT]
- MSTeamsChannel: Microsoft Teams Bot bidirectional messaging Channel

[POS]
MSTeams Bot channel implementation. Supports message edit/delete, Adaptive Card interactive
components, file attachments, typing indicator, and placeholder streaming progress.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import Request
from pydantic import ValidationError

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.providers.msteams.api import BotFrameworkApi
from app.channels.providers.msteams.auth import BotFrameworkJwtVerifier
from app.channels.providers.msteams.helpers import (
    EMOJI_TO_TEAMS_REACTION,
    build_adaptive_card_activity,
    decode_message_key,
    encode_message_key,
    extract_quote_context,
    strip_mention_tags,
)
from app.channels.providers.msteams.models import BotActivity
from app.channels.rendering.renderer import render
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 28000


class MSTeamsChannel(BaseChannel):
    """Microsoft Teams Bot channel using Bot Framework."""

    name = "teams"
    credential_spec = credential_spec(
        "teamsCredentials",
        app_id=credential_field("appId", "TEAMS_APP_ID"),
        app_password=credential_field("appPassword", "TEAMS_APP_PASSWORD"),
        tenant_id=credential_field("tenantId", "TEAMS_TENANT_ID"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=True,
        interactive_callback=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    def __init__(
        self,
        app_id: str,
        app_password: str,
        *,
        tenant_id: str = "",
        welcome_text: str = "",
        prompt_starters: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._app_id = app_id
        self._app_password = app_password
        self._tenant_id = tenant_id
        self._welcome_text = welcome_text
        self._prompt_starters = prompt_starters
        self._http = httpx.AsyncClient()
        self._api = BotFrameworkApi(app_id, app_password, self._http)
        self._jwt_verifier = BotFrameworkJwtVerifier(app_id, self._http)

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        if not self._app_id or not self._app_password:
            logger.info("MSTeams credentials not configured; channel idle")
            return
        try:
            await self._api.refresh_token()
        except Exception as exc:
            logger.warning("MSTeamsChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._http.aclose()
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        logger.info("MSTeamsChannel: started (app_id=%s)", self._app_id)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        self._api.clear_cache()
        await self._http.aclose()
        logger.info("MSTeamsChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            await self._api.ensure_token()
            return self._api.has_token
        except Exception:
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues = super().collect_issues()
        if not self._app_id:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="App ID is not configured",
                    fix="Set TEAMS_APP_ID or configure in Settings → Channels → MSTeams",
                )
            )
        if not self._app_password:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="App password is not configured",
                    fix="Set TEAMS_APP_PASSWORD or configure in Settings → Channels → MSTeams",
                )
            )
        if self._status == ChannelStatus.ERROR and not issues:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.AUTH,
                    severity=IssueSeverity.ERROR,
                    message="OAuth token acquisition failed",
                    fix="Verify App ID and password in Azure Bot registration",
                )
            )
        return issues

    # ── Outbound: send / edit / delete ─────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        service_url = str(msg.metadata.get("serviceUrl", "")) if msg.metadata else ""
        if not service_url:
            service_url = self._api.resolve_service_url(msg.recipient_id)
        conversation_id = msg.recipient_id

        has_components = bool(msg.components or msg.quick_replies)

        if msg.media:
            for ma in msg.media:
                await self._api.send_attachment(service_url, conversation_id, ma)

        if not msg.content and not has_components:
            return None

        if has_components:
            chunks = render(msg, self.render_style)
            text_body = "\n\n".join(chunks) if chunks else ""
            payload = build_adaptive_card_activity(
                msg.components,
                msg.quick_replies,
                text_body,
            )
            return await self._api.post_activity(service_url, conversation_id, payload)

        chunks = render(msg, self.render_style)
        last_id: str | None = None
        for chunk in chunks:
            mid = await self._api.send_text_activity(service_url, conversation_id, chunk)
            if mid:
                last_id = mid
        return last_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        decoded = decode_message_key(message_id)
        if decoded:
            activity_id, service_url, conversation_id = decoded
        else:
            activity_id = message_id
            service_url = self._api.resolve_service_url(chat_id)
            conversation_id = chat_id

        if not service_url:
            logger.debug("MSTeams edit: no service_url for conversation %s", chat_id)
            return

        await self._api.update_activity(
            service_url,
            conversation_id,
            activity_id,
            {"type": "message", "text": text},
        )

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        decoded = decode_message_key(message_id)
        if decoded:
            activity_id, service_url, conversation_id = decoded
        else:
            activity_id = message_id
            service_url = self._api.resolve_service_url(chat_id)
            conversation_id = chat_id

        if not service_url:
            logger.debug("MSTeams delete: no service_url for conversation %s", chat_id)
            return

        await self._api.delete_activity(service_url, conversation_id, activity_id)

    # ── Placeholder (streaming support) ────────────────────────

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        service_url = self._api.resolve_service_url(chat_id)
        if not service_url:
            return None
        await self._api.ensure_token()
        activity_id = await self._api.send_text_activity(service_url, chat_id, text)
        if not activity_id:
            return None
        return encode_message_key(activity_id, service_url, chat_id)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        chunks = render(msg, self.render_style)
        final_text = "\n\n".join(chunks) if chunks else msg.content
        await self.edit_message(chat_id, message_id, final_text)

    # ── Typing indicator ───────────────────────────────────────

    async def start_typing(self, chat_id: str) -> None:
        service_url = self._api.resolve_service_url(chat_id)
        if not service_url:
            return
        try:
            await self._api.send_typing(service_url, chat_id)
        except Exception:
            pass

    # ── Reaction ───────────────────────────────────────────────

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        reaction_type = EMOJI_TO_TEAMS_REACTION.get(emoji, "like") if emoji else ""
        if not reaction_type:
            return

        decoded = decode_message_key(message_id)
        if decoded:
            activity_id, service_url, conversation_id = decoded
        else:
            activity_id = message_id
            service_url = self._api.resolve_service_url(chat_id)
            conversation_id = chat_id

        if not service_url:
            return

        try:
            await self._api.add_reaction(service_url, conversation_id, activity_id, reaction_type)
        except Exception:
            pass

    # ── Inbound: activity processing ───────────────────────────

    async def handle_activity(self, activity: dict[str, object]) -> None:
        """Process a Bot Framework activity from the webhook endpoint."""
        try:
            act = BotActivity.model_validate(activity)
        except ValidationError:
            logger.debug("MSTeams: invalid activity payload, skipping")
            return

        conv_id = act.conversation.id if act.conversation else ""
        if act.service_url and conv_id:
            self._api.cache_service_url(conv_id, act.service_url)

        if act.type == "message":
            msg = self._parse_activity(act)
            if msg:
                await self._emit_inbound(msg)
        elif act.type == "invoke":
            await self._handle_invoke(act)
        elif act.type == "conversationUpdate":
            await self._handle_conversation_update(act)

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate Bot Framework JWT token."""
        auth_header = request.headers.get("authorization", "")
        try:
            activity = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            activity = {}

        if not await self._jwt_verifier.verify(auth_header, activity):
            trace_id = getattr(request.state, "_webhook_trace_id", "")
            raise WebhookResponseError(
                status_code=403,
                error_type="signature-invalid",
                title="Invalid Signature",
                detail="Bot Framework JWT verification failed",
                trace_id=trace_id,
            )

    async def verify_jwt(self, auth_header: str, activity: dict[str, object]) -> bool:
        """Verify Bot Framework JWT token from the webhook Authorization header."""
        return await self._jwt_verifier.verify(auth_header, activity)

    def _parse_activity(self, act: BotActivity) -> InboundMessage | None:
        sender_id = act.from_user.id if act.from_user else ""
        sender_name = act.from_user.name if act.from_user else ""

        if sender_id == self._app_id:
            return None

        text = strip_mention_tags(act.text)

        conv = act.conversation
        conv_id = conv.id if conv else ""
        is_group = conv.is_group if conv else False

        mentioned = self._check_bot_mentioned(act)
        media_list = self._parse_attachments(act)

        if not text.strip() and not media_list:
            return None

        reply_to_id = act.reply_to_id or None

        metadata: dict[str, object] = {
            "serviceUrl": act.service_url,
            "conversation_type": conv.conversation_type if conv else None,
        }

        quote_ctx = extract_quote_context([att.model_dump(by_alias=True) for att in act.attachments])
        if quote_ctx:
            metadata.update(quote_ctx)

        return self._build_inbound(
            sender_id=sender_id,
            content=text.strip(),
            chat_id=conv_id,
            sender_name=sender_name or None,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            reply_to_id=reply_to_id,
            metadata=metadata,
            message_id=act.id,
        )

    def _check_bot_mentioned(self, act: BotActivity) -> bool:
        for ent in act.entities:
            if ent.type != "mention":
                continue
            if ent.mentioned and ent.mentioned.id == self._app_id:
                return True
        return False

    def _parse_attachments(self, act: BotActivity) -> list[MediaAttachment]:
        result: list[MediaAttachment] = []
        for att in act.attachments:
            ct = att.content_type
            if ct.startswith("application/vnd.microsoft.card"):
                continue
            if ct.startswith("image/"):
                mt = MediaType.IMAGE
            elif "audio" in ct:
                mt = MediaType.AUDIO
            elif "video" in ct:
                mt = MediaType.VIDEO
            else:
                mt = MediaType.DOCUMENT
            if att.content_url:
                result.append(
                    MediaAttachment(
                        media_type=mt,
                        url=att.content_url,
                        filename=att.name,
                        mime_type=ct,
                    )
                )
        return result

    async def _handle_invoke(self, act: BotActivity) -> None:
        """Handle Adaptive Card Action.Submit invoke activities."""
        value = act.value
        if not value:
            return

        sender_id = act.from_user.id if act.from_user else ""
        conv_id = act.conversation.id if act.conversation else ""

        if value.get("quick_reply"):
            text = str(value["quick_reply"])
        elif value.get("action_id"):
            text = str(value["action_id"])
        else:
            return

        msg = self._build_inbound(
            sender_id=sender_id,
            content=text,
            chat_id=conv_id,
            message_id=act.id,
        )
        await self._emit_inbound(msg)

    async def _handle_conversation_update(self, act: BotActivity) -> None:
        """Send welcome card when bot is added to a conversation."""
        if not self._welcome_text and not self._prompt_starters:
            return

        if not act.members_added:
            return

        bot_id = act.recipient.id if act.recipient else self._app_id
        service_url = act.service_url
        conv_id = act.conversation.id if act.conversation else ""

        bot_was_added = any(m.id == bot_id for m in act.members_added)
        if not bot_was_added or not service_url or not conv_id:
            return

        conv_type = (act.conversation.conversation_type or "").lower() if act.conversation else ""
        is_personal = conv_type == "personal" or not conv_type

        try:
            await self._api.ensure_token()
            if is_personal and self._prompt_starters:
                payload = self._build_welcome_card()
                await self._api.post_activity(service_url, conv_id, payload)
            elif self._welcome_text:
                await self._api.send_text_activity(service_url, conv_id, self._welcome_text)
        except Exception:
            logger.debug("MSTeams: failed to send welcome message")

    def _build_welcome_card(self) -> dict[str, object]:
        """Build an Adaptive Card welcome message with prompt starters."""
        actions: list[dict[str, object]] = [
            {
                "type": "Action.Submit",
                "title": label,
                "data": {"msteams": {"type": "imBack", "value": label}},
            }
            for label in self._prompt_starters
        ]

        body: list[dict[str, object]] = []
        if self._welcome_text:
            body.append({"type": "TextBlock", "text": self._welcome_text, "wrap": True})

        card: dict[str, object] = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": body,
            "actions": actions,
        }

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }

    def register_routes(self, registrar: object) -> None:
        """Register custom HTTP routes for MS Teams Bot Framework webhook.

        Registers POST /webhook endpoint for receiving MS Teams Bot Framework activities.

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
            """Handle MS Teams Bot Framework activities."""
            import json

            try:
                ctx = await middleware.process_request(request, "teams")

                if ctx.parsed_data is None:

                    class _ErrorResponse:
                        status_code = 400
                        headers = {}
                        body = b"Invalid JSON"

                    return _ErrorResponse()

                await self.handle_activity(ctx.parsed_data)

            except WebhookResponseError as e:

                class _WebhookErrorResponse:
                    status_code = e.status_code
                    headers = {}
                    body = json.dumps(e.to_dict()).encode("utf-8")

                return _WebhookErrorResponse()
            except Exception as e:
                logger.warning("Teams webhook error: %s", e, exc_info=True)

                class _InternalErrorResponse:
                    status_code = 500
                    headers = {}
                    body = b"Internal error"

                return _InternalErrorResponse()

            class _SuccessResponse:
                status_code = 200
                headers = {}
                body = b""

            return _SuccessResponse()

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=webhook_handler,
            metadata=RouteMetadata(
                description="Handle MS Teams Bot Framework inbound activity",
                requires_auth=False,
                rate_limit_policy=RateLimitConfig(max_requests=60, window_seconds=60),
            ),
        )
