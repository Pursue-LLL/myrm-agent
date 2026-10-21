"""MSTeams inbound: Bot Framework activity parsing, JWT verification and the webhook route.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies _emit_inbound / _build_inbound)
- channels.providers.msteams.api::BotFrameworkApi (POS: HTTP/OAuth layer)
- channels.providers.msteams.auth::BotFrameworkJwtVerifier (POS: JWT verification)
- channels.providers.msteams.helpers (POS: HTML parsing, message encoding, Adaptive Card building)
- channels.providers.msteams.models::BotActivity (POS: Bot Framework activity payload model)

[OUTPUT]
- MSTeamsInboundMixin: handle_activity, verify / verify_jwt, activity and attachment parsing, invoke / conversationUpdate handling and register_routes used by MSTeamsChannel

[POS]
Inbound half of MSTeamsChannel. The host owns the credentials, the Bot Framework client and the JWT verifier; the mixin only turns activities into InboundMessage.
"""

from __future__ import annotations

import json
import logging

from fastapi import Request
from pydantic import ValidationError

from app.channels.core.base import BaseChannel
from app.channels.providers.msteams.api import BotFrameworkApi
from app.channels.providers.msteams.auth import BotFrameworkJwtVerifier
from app.channels.providers.msteams.helpers import (
    extract_quote_context,
    strip_mention_tags,
)
from app.channels.providers.msteams.models import BotActivity
from app.channels.security.errors import WebhookResponseError
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
)

logger = logging.getLogger(__name__)


class MSTeamsInboundMixin(BaseChannel):
    """Bot Framework activity handling for ``MSTeamsChannel``.

    Requires the host class to provide the attributes below.
    """

    _app_id: str
    _welcome_text: str
    _prompt_starters: tuple[str, ...]
    _api: BotFrameworkApi
    _jwt_verifier: BotFrameworkJwtVerifier

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
