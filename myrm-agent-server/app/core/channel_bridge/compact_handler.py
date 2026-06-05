"""CompactHandler implementation for IM /compact command.

[INPUT]
- app.channels.protocols.compact::CompactHandler, CompactResult
- app.channels.types::InboundMessage
- app.core.channel_bridge.agent_executor::resolve_session_key
- app.core.channel_bridge.config_loader::load_user_configs
- app.core.channel_bridge.config_parsers::extract_session_policy, session_policy_from_agent_dict
- app.core.channel_bridge.topic_config::SqlTopicManager
- app.database.connection::get_session
- app.services.chat.chat_service::ChatService
- app.services.chat.compact_service::compact_chat

[OUTPUT]
- ChannelCompactHandler: Business-layer CompactHandler implementation

[POS]
Maps the framework-level CompactHandler protocol to the application compact_service.
"""

from __future__ import annotations

from app.channels.protocols.compact import CompactResult
from app.channels.types import InboundMessage, SessionPolicy
from app.core.channel_bridge.agent_executor import resolve_session_key
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import (
    extract_session_policy,
    session_policy_from_agent_dict,
)
from app.database.connection import get_session
from app.services.chat.chat_service import ChatService
from app.services.chat.compact_service import compact_chat


class ChannelCompactHandler:
    """Business-layer CompactHandler for /compact command."""

    async def __call__(self, msg: InboundMessage, user_id: str, *, focus_topic: str = "") -> CompactResult:
        configs = await load_user_configs()
        session_policy = SessionPolicy()
        if configs.personal_settings_dict:
            session_policy = extract_session_policy(configs.personal_settings_dict)

        agent_id = await self._resolve_bound_agent_id(msg)

        if agent_id:
            from app.services.agent.profile_resolver import get_agent_profile_resolver

            profile = await get_agent_profile_resolver().resolve(agent_id)
            if profile and profile.session_policy and isinstance(profile.session_policy, dict):
                session_policy = session_policy_from_agent_dict(profile.session_policy)

        session_key = await resolve_session_key(msg, session_policy, agent_id=agent_id)

        async with get_session() as db:
            chat = await ChatService.get_or_create_channel_chat(
                "sandbox",
                session_key,
                msg.channel,
            )
            return await compact_chat(db, chat.id, focus_topic=focus_topic)

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
