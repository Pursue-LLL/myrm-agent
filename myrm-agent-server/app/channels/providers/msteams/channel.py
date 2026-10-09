"""Microsoft Teams channel — bidirectional messaging via Bot Framework.

Inbound: HTTP webhook (Bot Framework activity) → _parse_activity → _emit_inbound
  - Text, file attachments, mentions, quote/reply context
  - 1:1 and group chat/team channel support
  - Adaptive Card invoke callbacks (interactive components)
Outbound: Bot Framework connector API (text/adaptive card/file attachment)

[INPUT]
- channels.core.attachment_delivery::deliver_attachments (POS: per-attachment delivery with aggregated failure)
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.providers.msteams.api::BotFrameworkApi (POS: HTTP/OAuth layer)
- channels.providers.msteams.helpers (POS: HTML parsing, message encoding, Adaptive Card building)
- channels.providers.msteams.auth::BotFrameworkJwtVerifier (POS: JWT verification)
- channels.providers.msteams.inbound::MSTeamsInboundMixin (POS: activity parsing, JWT verification and the webhook route)

[OUTPUT]
- MSTeamsChannel: Microsoft Teams Bot bidirectional messaging Channel (credentials, lifecycle, outbound); inbound comes from the mixin

[POS]
MSTeams Bot channel implementation. Supports message edit/delete, Adaptive Card interactive
components, file attachments, typing indicator, and placeholder streaming progress.
"""

from __future__ import annotations

import logging
from functools import partial

import httpx

from app.channels.core.attachment_delivery import deliver_attachments
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.msteams.api import BotFrameworkApi
from app.channels.providers.msteams.auth import BotFrameworkJwtVerifier
from app.channels.providers.msteams.helpers import (
    EMOJI_TO_TEAMS_REACTION,
    build_adaptive_card_activity,
    decode_message_key,
    encode_message_key,
)
from app.channels.providers.msteams.inbound import MSTeamsInboundMixin
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

_MAX_TEXT_LENGTH = 28000


class MSTeamsChannel(MSTeamsInboundMixin, BaseChannel):
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

        last_id: str | None = None
        if has_components:
            chunks = render(msg, self.render_style)
            text_body = "\n\n".join(chunks) if chunks else ""
            payload = build_adaptive_card_activity(
                msg.components,
                msg.quick_replies,
                text_body,
            )
            last_id = await self._api.post_activity(service_url, conversation_id, payload)
        elif msg.content:
            for chunk in render(msg, self.render_style):
                last_id = await self._api.send_text_activity(service_url, conversation_id, chunk) or last_id

        attachment_id = await deliver_attachments(
            self.name,
            msg.media,
            partial(self._api.send_attachment, service_url, conversation_id),
            text_delivered=has_components or bool(msg.content),
        )
        return last_id or attachment_id

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
        try:
            activity_id = await self._api.send_text_activity(service_url, chat_id, text)
        except ChannelSendError as exc:
            logger.warning("MSTeams placeholder failed: %s", exc)
            return None
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
        final_text = chunks[0] if chunks else (msg.content or "")
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










