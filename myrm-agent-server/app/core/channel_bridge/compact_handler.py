"""CompactHandler implementation for IM /compact command.

[INPUT]
- app.channels.protocols.compact::CompactHandler, CompactResult, CompactSkip
- app.channels.types::InboundMessage
- app.core.channel_bridge.command_session::resolve_command_session_key (POS: Session key a message's conversation is stored under)
- app.database.connection::get_session
- app.services.chat.chat_service::ChatService
- app.services.chat.compact_service::compact_chat, CompactReason, CompactResult

[OUTPUT]
- ChannelCompactHandler: Business-layer CompactHandler implementation

[POS]
Maps the framework-level CompactHandler protocol to the application compact_service. A person's /compact is an
explicit request, so the anti-thrash guard that holds back automatic compaction does not stop it; the service's
reason code becomes the channel's ``CompactSkip`` category, which the framework words in the reader's language.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.channels.protocols.compact import CompactResult, CompactSkip
from app.channels.types import InboundMessage
from app.core.channel_bridge.command_session import resolve_command_session_key
from app.database.connection import get_session
from app.services.chat.chat_service import ChatService
from app.services.chat.compact_service import CompactReason, compact_chat
from app.services.chat.compact_service import CompactResult as ServiceCompactResult

# Only reasons known to be no failure are worded as such; every other reason, and any added later, reads as a failure.
_SKIP_BY_REASON: Mapping[str, CompactSkip] = {
    CompactReason.NO_COMPACTABLE_MESSAGES: CompactSkip.NOTHING_TO_COMPACT,
    CompactReason.TOO_FEW_MESSAGES: CompactSkip.NOTHING_TO_COMPACT,
    CompactReason.CONCURRENT_COMPACTION: CompactSkip.BUSY,
    CompactReason.SUMMARIZE_CIRCUIT_OPEN: CompactSkip.PAUSED,
}


def _to_channel_result(result: ServiceCompactResult) -> CompactResult:
    """The service's outcome in the channel's terms: the counts stay, the reason code becomes a category a reply can word."""
    return CompactResult(
        compacted=result.compacted,
        message_count=result.message_count,
        tokens_saved=result.tokens_saved,
        skip=None if result.compacted else _SKIP_BY_REASON.get(result.reason or "", CompactSkip.FAILED),
    )


class ChannelCompactHandler:
    """Business-layer CompactHandler for /compact command."""

    async def __call__(self, msg: InboundMessage, user_id: str, *, focus_topic: str = "") -> CompactResult:
        session_key = await resolve_command_session_key(msg)

        async with get_session() as db:
            chat = await ChatService.get_or_create_channel_chat(session_key, msg.channel)
            result = await compact_chat(db, chat.id, focus_topic=focus_topic, explicit_request=True)
        return _to_channel_result(result)
