"""Feishu inbound: webhook / websocket event handling for messages, card actions, reactions and comments.

[INPUT]
- channels.providers.feishu.parser::parse_inbound_event, extract_message_text (POS: inbound event parser)
- channels.providers.feishu.cards::parse_card_action (POS: card action parser)
- channels.providers.feishu.models::FeishuWebhookPayload, FeishuCardEvent (POS: webhook payload models)
- channels.providers.feishu.reactions::FEISHU_EMOJI_TO_UNICODE (POS: reaction emoji vocabulary)
- channels.providers.feishu.user_resolver::FeishuUserResolver (POS: sender display-name resolution)

[OUTPUT]
- FeishuInboundMixin: handle_webhook_event and the reply-context / sender-name / inbound-media resolvers used by FeishuChannel

[POS]
Inbound half of FeishuChannel. The host owns the API client and the transport; the mixin only converts events into InboundMessage.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.channels.types import (
    MediaAttachment,
    MediaType,
    ReplyContext,
)

from .api import FeishuClient
from .cards import (
    parse_card_action,
)
from .models import FeishuCardEvent, FeishuWebhookPayload
from .parser import FeishuInboundEvent, extract_message_text, parse_inbound_event
from .reactions import FEISHU_EMOJI_TO_UNICODE
from .user_resolver import FeishuUserResolver

logger = logging.getLogger(__name__)

_MAX_MEDIA_CONCURRENCY = 3


class FeishuInboundMixin:
    """Feishu inbound event handling for ``FeishuChannel``.

    Requires the host class to provide the attributes below plus ``_emit_inbound`` / ``_build_inbound``
    from ``BaseChannel``.
    """

    _client: FeishuClient
    _user_resolver: FeishuUserResolver

    async def handle_webhook_event(self, event_data: dict[str, object]) -> dict[str, object] | None:
        """Process a Feishu event callback (URL verify / message / card action / comment)."""
        try:
            payload = FeishuWebhookPayload.model_validate(event_data)
        except ValidationError:
            logger.debug("Feishu webhook payload validation failed")
            return None

        if payload.challenge is not None:
            return {"challenge": payload.challenge}

        event_type = payload.header.event_type

        if event_type == "im.message.receive_v1":
            parsed = parse_inbound_event(event_data, bot_open_id=self._client.bot_open_id)
            if parsed and parsed.sender_id != self._client.bot_open_id:
                reply_to = await self._fetch_reply_context(parsed.parent_id)
                content = parsed.content
                media = await self._resolve_inbound_media(parsed)

                sent_at = __import__("time").time()
                create_time = payload.header.create_time
                if create_time:
                    try:
                        sent_at = float(create_time) / 1000.0
                    except (ValueError, TypeError):
                        pass

                # Check numbered action fallback resolution for localhost/intranet environments
                from .action_fallback import default_action_fallback_registry

                resolved_action_id = default_action_fallback_registry.resolve_action(
                    chat_id=parsed.chat_id,
                    user_id=parsed.sender_id,
                    input_text=content,
                )

                metadata: dict[str, object] = {
                    "message_id": parsed.message_id,
                    "msg_type": parsed.msg_type,
                    "image_keys": parsed.image_keys,
                    "media_keys": parsed.media_keys,
                }

                if resolved_action_id:
                    # Upgrade text reply to structured card action event
                    content = resolved_action_id
                    metadata["callback_type"] = "act"
                    metadata["action_id"] = resolved_action_id
                    metadata["fallback_resolved"] = True

                inbound = self._build_inbound(
                    sender_id=parsed.sender_id,
                    content=content,
                    sent_at=sent_at,
                    sent_timezone="UTC",
                    chat_id=parsed.chat_id,
                    is_group=parsed.is_group,
                    is_bot=parsed.sender_type in ("bot", "app"),
                    mentioned=parsed.bot_mentioned or bool(resolved_action_id),
                    media=media,
                    message_id=parsed.message_id,
                    thread_id=parsed.root_id,
                    reply_to=reply_to,
                    sender_name=await self._resolve_sender_name(parsed.sender_id),
                    metadata=metadata,
                )
                await self._emit_inbound(inbound)

        elif event_type == "card.action.trigger":
            try:
                card_evt = FeishuCardEvent.model_validate(payload.event)
            except ValidationError:
                logger.debug("Feishu card event validation failed")
                return {"toast": {"type": "info", "content": ""}}

            result = parse_card_action(card_evt.model_dump())
            if result:
                sender_id, chat_id, content, metadata = result
                if sender_id != self._client.bot_open_id and content:
                    sent_at = __import__("time").time()
                    create_time = payload.header.create_time
                    if create_time:
                        try:
                            sent_at = float(create_time) / 1000.0
                        except (ValueError, TypeError):
                            pass

                    inbound = self._build_inbound(
                        sender_id=sender_id,
                        content=content,
                        sent_at=sent_at,
                        sent_timezone="UTC",
                        chat_id=chat_id,
                        is_group=False,
                        mentioned=False,
                        sender_name=await self._resolve_sender_name(sender_id),
                        metadata=metadata,
                    )
                    await self._emit_inbound(inbound)
            return {"toast": {"type": "info", "content": ""}}

        elif event_type == "im.message.reaction_created_v1":
            await self._handle_reaction_event(payload.event)

        elif event_type == "drive.notice.comment_add_v1":
            from .comment_handler import CommentHandler

            handler = CommentHandler(self._client, self._client.bot_open_id)
            await handler.handle_comment_event(payload.event, self)

        return None

    async def _handle_reaction_event(self, event: dict[str, object]) -> None:
        """Convert a Feishu im.message.reaction_created_v1 event to InboundMessage."""
        if not isinstance(event, dict):
            return

        message_id = str(event.get("message_id", ""))
        if not message_id:
            return

        reaction_type = event.get("reaction_type")
        emoji_type = ""
        if isinstance(reaction_type, dict):
            emoji_type = str(reaction_type.get("emoji_type", ""))
        if not emoji_type:
            return

        emoji = FEISHU_EMOJI_TO_UNICODE.get(emoji_type, "")
        if not emoji:
            return

        operator_type = event.get("operator_type")
        sender_id = ""
        if isinstance(operator_type, dict):
            operator_id = operator_type.get("operator_id")
            if isinstance(operator_id, dict):
                sender_id = str(operator_id.get("open_id", ""))
        if not sender_id or sender_id == self._client.bot_open_id:
            return

        inbound = self._build_inbound(
            sender_id=sender_id,
            content=emoji,
            chat_id=sender_id,
            is_group=False,
            mentioned=True,
            sender_name=await self._resolve_sender_name(sender_id),
            message_id=message_id,
            metadata={"reaction": True, "target_message_id": message_id},
        )
        await self._emit_inbound(inbound)

    async def _fetch_reply_context(self, parent_id: str | None) -> ReplyContext | None:
        """Fetch replied-to message and parse into structured ReplyContext.

        Retrieves parent message via Feishu API, extracts text content and media.
        Returns: ReplyContext with message content, media attachments, sender info.
        """
        if not parent_id:
            return None
        try:
            msg_obj = await self._client.get_message(parent_id)
            if not msg_obj:
                return None

            text = extract_message_text(msg_obj)
            content = text if text else ""

            media_list: list[MediaAttachment] = []
            msg_type = str(msg_obj.get("msg_type", ""))
            if msg_type == "image":
                media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
            elif msg_type == "file":
                media_list.append(MediaAttachment(media_type=MediaType.DOCUMENT))
            elif msg_type == "audio":
                media_list.append(MediaAttachment(media_type=MediaType.AUDIO))
            elif msg_type == "media":
                media_list.append(MediaAttachment(media_type=MediaType.VIDEO))

            sender_info = msg_obj.get("sender", {})
            sender_id = sender_info.get("sender_id", {}).get("open_id") if isinstance(sender_info, dict) else None

            timestamp = None
            create_time = msg_obj.get("create_time")
            if create_time:
                try:
                    timestamp = float(create_time) / 1000.0
                except (ValueError, TypeError):
                    pass

            return ReplyContext(
                message_id=parent_id,
                content=content,
                media=tuple(media_list),
                sender_id=sender_id,
                sender_name=await self._resolve_sender_name(sender_id),
                timestamp=timestamp,
            )
        except Exception:
            logger.debug("Failed to fetch reply context for %s", parent_id)
            return None

    async def _resolve_sender_name(self, sender_id: str | None) -> str | None:
        """Resolve a Feishu sender's display name via contact API (fail-open).

        Returns None when the ID is missing, resolution fails, or the user
        cannot be found — callers fall back to the opaque open_id.
        """
        if not sender_id:
            return None
        try:
            return await self._user_resolver.resolve_user(sender_id)
        except Exception:
            logger.debug("Failed to resolve Feishu sender name for %s", sender_id)
            return None

    async def _resolve_inbound_media(
        self,
        parsed: FeishuInboundEvent,
    ) -> tuple[MediaAttachment, ...]:
        """Download image/media resources referenced in an inbound event.

        Uses a concurrency semaphore to avoid overwhelming the Feishu API
        with parallel downloads.  Individual download failures are logged
        and skipped so the message is still delivered.
        """
        if not parsed.image_keys and not parsed.media_keys:
            return ()

        sem = asyncio.Semaphore(_MAX_MEDIA_CONCURRENCY)
        tmp_dir = Path(tempfile.gettempdir()) / "feishu_media"
        tmp_dir.mkdir(exist_ok=True)

        async def _download_image(key: str) -> MediaAttachment | None:
            async with sem:
                try:
                    if parsed.message_id:
                        data = await self._client.download_message_resource(
                            parsed.message_id,
                            key,
                            "image",
                        )
                    else:
                        data = await self._client.download_image(key)
                    if not data:
                        return None
                    path = tmp_dir / f"{key}.jpg"
                    path.write_bytes(data)
                    return MediaAttachment(
                        media_type=MediaType.IMAGE,
                        path=str(path),
                        filename=f"{key}.jpg",
                        mime_type="image/jpeg",
                    )
                except Exception:
                    logger.warning("Feishu image download failed: %s", key)
                    return None

        async def _download_file(
            file_key: str,
            file_name: str | None,
        ) -> MediaAttachment | None:
            async with sem:
                try:
                    if not parsed.message_id:
                        return None
                    data = await self._client.download_message_resource(
                        parsed.message_id,
                        file_key,
                        "file",
                    )
                    if not data:
                        return None
                    name = file_name or file_key
                    path = tmp_dir / name
                    path.write_bytes(data)
                    return MediaAttachment(
                        media_type=MediaType.DOCUMENT,
                        path=str(path),
                        filename=name,
                    )
                except Exception:
                    logger.warning("Feishu media download failed: %s", file_key)
                    return None

        tasks: list[asyncio.Task[MediaAttachment | None]] = []
        for key in parsed.image_keys:
            tasks.append(asyncio.create_task(_download_image(key)))
        for file_key, file_name in parsed.media_keys:
            tasks.append(asyncio.create_task(_download_file(file_key, file_name)))

        results = await asyncio.gather(*tasks)
        return tuple(att for att in results if att is not None)
