"""CompactHandler implementation for IM /compact command.

[INPUT]
- app.channels.protocols.compact::CompactHandler, CompactResult, CompactSkip
- app.channels.types::InboundMessage
- app.core.channel_bridge.agent_executor::resolve_session_key
- app.core.channel_bridge.config_loader::load_user_configs
- app.core.channel_bridge.config_parsers::extract_session_policy, session_policy_from_agent_dict
- app.core.channel_bridge.topic_config::SqlTopicManager
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
from app.channels.types import InboundMessage, SessionPolicy
from app.core.channel_bridge.agent_executor import resolve_session_key
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import (
    extract_session_policy,
    session_policy_from_agent_dict,
)
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
        configs = await load_user_configs()
        session_policy = SessionPolicy()
        if configs.personal_settings_dict:
            session_policy = extract_session_policy(configs.personal_settings_dict)

        agent_id = await self._resolve_bound_agent_id(msg)

        if agent_id:
            from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

            profile = await get_agent_profile_resolver().resolve(agent_id)
            if profile and profile.session_policy and isinstance(profile.session_policy, dict):
                session_policy = session_policy_from_agent_dict(profile.session_policy)

        session_key = await resolve_session_key(msg, session_policy, agent_id=agent_id)

        async with get_session() as db:
            chat = await ChatService.get_or_create_channel_chat(session_key, msg.channel)
            result = await compact_chat(db, chat.id, focus_topic=focus_topic, explicit_request=True)
        return _to_channel_result(result)

    @staticmethod
    async def _resolve_bound_agent_id(msg: InboundMessage) -> str | None:
        """Resolve the agent_id bound to the current channel/topic."""
        from app.core.channel_bridge.topic_config import SqlTopicManager

        topic_mgr = SqlTopicManager()
        chat_id = msg.chat_id or msg.sender_id
        if not chat_id:
            return None

        if msg.thread_id:
            ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, msg.thread_id)
            if ctx and ctx.agent_id:
                return ctx.agent_id

        ctx = await topic_mgr.resolve_topic(msg.channel, chat_id, None)
        if ctx and ctx.agent_id:
            return ctx.agent_id

        ctx = await topic_mgr.resolve_topic(msg.channel, "__global__", None)
        if ctx and ctx.agent_id:
            return ctx.agent_id

        return None
