"""[INPUT]
- .common (POS: shared constants and helpers)

[OUTPUT]
- PolicyMixin

[POS]
Topic manager mixin: read paths, agent-id resolution and channel-bindability checks.
"""

from __future__ import annotations

from .common import (
    SEARCH_AGENT_CHANNEL_BIND_MSG,
    logger,
)


class PolicyMixin:
    async def get_all_topics(self, channel: str) -> dict[str, object]:
        """Get all topics for a channel (used by API).

        Strips legacy Search-track bindings so Settings never shows ghost binds.
        """
        config = await self._load_config(channel)
        if await self._sanitize_unbindable_bindings(channel, config):
            await self._save_config(channel, config)
        return config

    async def _resolve_agent_id(self, agent_id_or_name: str) -> str:
        """Resolve agent by UUID or name. Returns the canonical UUID.

        Raises:
            ValueError: when input is not a valid UUID and name lookup finds nothing.
        """
        import uuid as _uuid

        from app.platform_utils import get_session_factory
        from app.services.agent.agent_service import AgentService

        session_factory = get_session_factory()
        async with session_factory() as _db:
            agent = await AgentService.resolve_agent(agent_id_or_name)
            if agent:
                return str(agent.id)

        try:
            _uuid.UUID(agent_id_or_name)
        except ValueError:
            raise ValueError(f"Agent not found: '{agent_id_or_name}'") from None

        return agent_id_or_name

    @staticmethod
    def _delete_binding_keys(
        config: dict[str, object],
        chat_id: str,
        storage_key: str,
    ) -> bool:
        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict) or storage_key not in group_topics:
            return False
        del group_topics[storage_key]
        if not group_topics:
            del config[chat_id]
        return True

    async def _is_channel_bindable_agent(self, agent_id: str) -> bool:
        """Return False for Search-track or missing agents (Channel/IM = General-only)."""
        from app.services.agent.agent_service import AgentService

        agent = await AgentService.get_agent_by_id(agent_id)
        if agent is None:
            return False
        return not self._agent_is_search_track(agent)

    @staticmethod
    def _agent_is_search_track(agent: object) -> bool:
        meta = getattr(agent, "metadata", None)
        if not isinstance(meta, dict):
            return False
        return str(meta.get("prompt_mode", "full")) == "search"

    async def _sanitize_unbindable_bindings(self, channel: str, config: dict[str, object]) -> bool:
        changed = False
        for chat_id, group_topics in list(config.items()):
            if not isinstance(group_topics, dict):
                continue
            chat_id_str = str(chat_id)
            for storage_key, topic_cfg in list(group_topics.items()):
                if not isinstance(topic_cfg, dict):
                    continue
                raw_agent_id = topic_cfg.get("agentId")
                if not isinstance(raw_agent_id, str) or not raw_agent_id:
                    continue
                if await self._is_channel_bindable_agent(raw_agent_id):
                    continue
                self._delete_binding_keys(config, chat_id_str, str(storage_key))
                logger.info(
                    "SqlTopicManager: unbindable agent %s binding %s/%s/%s auto-removed",
                    raw_agent_id,
                    channel,
                    chat_id_str,
                    storage_key,
                )
                changed = True
        return changed

    async def _assert_channel_bindable_agent(self, agent_id: str) -> None:
        """Reject Search-track agents — Channel/IM always runs General CORE."""
        from app.services.agent.agent_service import AgentService

        agent = await AgentService.get_agent_by_id(agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_id}")
        if self._agent_is_search_track(agent):
            raise ValueError(SEARCH_AGENT_CHANNEL_BIND_MSG)
