"""Topic manager — reads/writes per-topic/channel configuration from UserConfig.

Implements TopicManager protocol for the business layer.
Manages topic/channel configuration in the per-channel topics config key
in UserConfig, with a TTL cache to avoid repeated DB queries.

Features:
- Dual-granularity binding: per-thread (forum topics) and per-channel
- Agent name resolution: /bind accepts UUID or name, stores canonical UUID
- Lazy expiration: idle timeout + max age checked at resolve time (no bg tasks)
- Activity tracking: in-memory cache with interval flush to reduce DB writes
- Auto-discovery: sync_topic_metadata with dirty checking for UI display

[INPUT]
- app.database.models::UserConfig
- app.services.agent.agent_service::AgentService (for name resolution)
- app.channels.types::TopicContext

[OUTPUT]
- SqlTopicManager: TopicManager implementation backed by UserConfig DB

[POS]
业务层的话题/频道管理器。从 UserConfig 表读写每个 channel 的
per-topic/per-channel 配置，为 AgentRouter 提供路由决策数据，
支持 /bind /unbind 命令的持久化，以及智能体删除时的级联清理。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.channels.types import TopicContext
from app.channels.types.thread_sharing import ThreadSharingMode

logger = logging.getLogger(__name__)

_CACHE_TTL = 60.0

_CHANNEL_LEVEL_KEY = "__channel__"

_DEFAULT_IDLE_TIMEOUT_HOURS = 24
_ACTIVE_FLUSH_INTERVAL = 300.0


class SqlTopicManager:
    """Manages per-topic/channel configuration in UserConfig DB.

    Config structure in UserConfig (config_key = "telegramTopics" etc.):
    {
        "<chat_id>": {
            "<thread_id>": {
                "agentId": "uuid-of-agent",
                "enabled": true,
                "boundAt": "2026-03-06T12:00:00Z",
                "lastActiveAt": "2026-03-30T12:00:00Z",
                "idleTimeoutH": 24,
                "maxAgeH": null
            },
            "__channel__": { ... }
        }
    }
    """

    def __init__(
        self,
        idle_timeout_hours: int = _DEFAULT_IDLE_TIMEOUT_HOURS,
        max_age_hours: int | None = None,
    ) -> None:
        self._cache: dict[str, dict[str, object]] = {}
        self._cache_ts: dict[str, float] = {}
        self._default_idle_timeout_h = idle_timeout_hours
        self._default_max_age_h = max_age_hours
        self._active_mem: dict[str, str] = {}
        self._active_flush_ts: dict[str, float] = {}

    async def resolve_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> TopicContext | None:
        config = await self._load_config(channel)
        if not config:
            return None

        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict):
            return None

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        topic_cfg = group_topics.get(storage_key)
        if not isinstance(topic_cfg, dict):
            return None

        if self._is_expired(topic_cfg):
            del group_topics[storage_key]
            if not group_topics:
                del config[chat_id]
            await self._save_config(channel, config)
            logger.info("SqlTopicManager: expired binding %s/%s/%s auto-removed", channel, chat_id, storage_key)
            return None

        await self._touch_active(channel, chat_id, storage_key, config)

        return TopicContext(
            topic_id=thread_id or chat_id,
            agent_id=str(topic_cfg["agentId"]) if topic_cfg.get("agentId") else None,
            enabled=bool(topic_cfg.get("enabled", True)),
            bound_at=str(topic_cfg["boundAt"]) if topic_cfg.get("boundAt") else None,
            thread_sharing_mode=str(topic_cfg.get("threadSharingMode", "isolated")),
        )

    async def bind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        agent_id: str | None = None,
        display_name: str | None = None,
        avatar_url: str | None = None,
        thread_sharing_mode: ThreadSharingMode = ThreadSharingMode.ISOLATED,
    ) -> TopicContext:
        resolved_agent_id = agent_id
        if agent_id:
            resolved_agent_id = await self._resolve_agent_id(agent_id)

        now_iso = datetime.now(timezone.utc).isoformat()
        topic_entry: dict[str, object] = {
            "enabled": True,
            "boundAt": now_iso,
            "lastActiveAt": now_iso,
            "idleTimeoutH": self._default_idle_timeout_h,
            "threadSharingMode": thread_sharing_mode,
        }
        if self._default_max_age_h is not None:
            topic_entry["maxAgeH"] = self._default_max_age_h
        if resolved_agent_id:
            topic_entry["agentId"] = resolved_agent_id
        if display_name is not None:
            topic_entry["displayName"] = display_name
        if avatar_url is not None:
            topic_entry["avatarUrl"] = avatar_url

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        await self._upsert_topic(channel, chat_id, storage_key, topic_entry)

        return TopicContext(
            topic_id=thread_id or chat_id,
            agent_id=resolved_agent_id,
            enabled=True,
            bound_at=now_iso,
            thread_sharing_mode=thread_sharing_mode,
        )

    def _is_expired(self, topic_cfg: dict[str, object]) -> bool:
        """Check if a binding has expired (idle timeout or max age)."""
        now = datetime.now(timezone.utc)

        idle_h = topic_cfg.get("idleTimeoutH")
        if isinstance(idle_h, (int, float)) and idle_h > 0:
            last_active_raw = topic_cfg.get("lastActiveAt")
            if isinstance(last_active_raw, str):
                try:
                    last_active = datetime.fromisoformat(last_active_raw)
                    if (now - last_active).total_seconds() > idle_h * 3600:
                        return True
                except (ValueError, TypeError):
                    pass

        max_age_h = topic_cfg.get("maxAgeH")
        if isinstance(max_age_h, (int, float)) and max_age_h > 0:
            bound_raw = topic_cfg.get("boundAt")
            if isinstance(bound_raw, str):
                try:
                    bound = datetime.fromisoformat(bound_raw)
                    if (now - bound).total_seconds() > max_age_h * 3600:
                        return True
                except (ValueError, TypeError):
                    pass

        return False

    async def _touch_active(self, channel: str, chat_id: str, storage_key: str, config: dict[str, object]) -> None:
        """Update last-active timestamp in cache and persist to DB at intervals."""
        mem_key = f"{channel}:{chat_id}:{storage_key}"
        now_mono = time.monotonic()

        last_flush = self._active_flush_ts.get(mem_key, 0.0)
        if now_mono - last_flush < _ACTIVE_FLUSH_INTERVAL:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        self._active_mem[mem_key] = now_iso
        self._active_flush_ts[mem_key] = now_mono

        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict):
            return
        topic_cfg = group_topics.get(storage_key)
        if isinstance(topic_cfg, dict):
            topic_cfg["lastActiveAt"] = now_iso
            await self._save_config(channel, config)

    async def remove_agent_from_all_bindings(self, agent_id: str) -> None:
        """Remove an agent from all channel and topic bindings (cascading delete)."""
        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models import UserConfig

            async with get_session() as session:
                result = await session.execute(select(UserConfig).where(UserConfig.config_key.like("%Topics")))
                rows = result.scalars().all()

                changed_channels = []
                for row in rows:
                    config = row.config_value
                    if not isinstance(config, dict):
                        continue

                    changed = False
                    for chat_id, group_topics in list(config.items()):
                        if not isinstance(group_topics, dict):
                            continue

                        for storage_key, topic_cfg in list(group_topics.items()):
                            if isinstance(topic_cfg, dict) and topic_cfg.get("agentId") == agent_id:
                                # Remove the binding completely
                                del group_topics[storage_key]
                                changed = True

                        # Clean up empty chat groups
                        if not group_topics:
                            del config[chat_id]
                            changed = True

                    if changed:
                        row.config_value = config
                        session.add(row)
                        # Extract channel name from config_key (e.g., "telegramTopics" -> "telegram")
                        channel_name = row.config_key[:-6] if row.config_key.endswith("Topics") else row.config_key
                        changed_channels.append(channel_name)

                if changed_channels:
                    await session.commit()
                    for channel in changed_channels:
                        self._invalidate_cache(channel)
                        logger.info("SqlTopicManager: Cascaded deletion of agent %s from channel %s", agent_id, channel)

        except Exception as exc:
            logger.warning("SqlTopicManager: failed to cascade delete agent %s: %s", agent_id, exc)

    async def get_all_topics(self, channel: str) -> dict[str, object]:
        """Get all topics for a channel (used by API)."""
        return await self._load_config(channel)

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

    async def sync_topic_metadata(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        if display_name is None and avatar_url is None:
            return

        config = await self._load_config(channel)
        group_raw = config.get(chat_id)
        if not isinstance(group_raw, dict):
            group_topics: dict[str, object] = {}
            config[chat_id] = group_topics
        else:
            group_topics = group_raw

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        topic_raw = group_topics.get(storage_key)
        if not isinstance(topic_raw, dict):
            topic_cfg: dict[str, object] = {}
            group_topics[storage_key] = topic_cfg
        else:
            topic_cfg = topic_raw

        changed = False
        if display_name is not None and topic_cfg.get("displayName") != display_name:
            topic_cfg["displayName"] = display_name
            changed = True
        if avatar_url is not None and topic_cfg.get("avatarUrl") != avatar_url:
            topic_cfg["avatarUrl"] = avatar_url
            changed = True

        if changed:
            await self._save_config(channel, config)

    async def unbind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> bool:
        config = await self._load_config(channel)
        group_topics = config.get(chat_id)
        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        if not isinstance(group_topics, dict) or storage_key not in group_topics:
            return False

        del group_topics[storage_key]
        if not group_topics:
            del config[chat_id]

        await self._save_config(channel, config)
        return True

    async def _upsert_topic(
        self,
        channel: str,
        chat_id: str,
        storage_key: str,
        topic_entry: dict[str, object],
    ) -> None:
        config = await self._load_config(channel)

        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict):
            group_topics = {}
            config[chat_id] = group_topics

        group_topics[storage_key] = topic_entry
        await self._save_config(channel, config)

    async def _save_config(self, channel: str, config: dict[str, object]) -> None:
        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models import UserConfig

            config_key = f"{channel}Topics"
            async with get_session() as session:
                result = await session.execute(
                    select(UserConfig).where(
                        UserConfig.config_key == config_key,
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    row.config_value = config
                else:
                    session.add(
                        UserConfig(
                            id=__import__("nanoid").generate(size=21),
                            config_key=config_key,
                            config_value=config,
                            version="1_0",
                            last_device_id="server",
                        )
                    )
                await session.commit()

            self._invalidate_cache(channel)
        except Exception as exc:
            logger.warning("SqlTopicManager: failed to save %s topics: %s", channel, exc)

    async def _load_config(self, channel: str) -> dict[str, object]:
        now = time.monotonic()
        cached_ts = self._cache_ts.get(channel, 0.0)
        if now - cached_ts < _CACHE_TTL and channel in self._cache:
            return self._cache[channel]

        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models import UserConfig

            config_key = f"{channel}Topics"
            async with get_session() as session:
                result = await session.execute(
                    select(UserConfig.config_value).where(
                        UserConfig.config_key == config_key,
                    )
                )
                row = result.scalar_one_or_none()

            self._cache_ts[channel] = now
            data = row if isinstance(row, dict) else {}
            self._cache[channel] = data
            return data
        except Exception as exc:
            logger.warning("SqlTopicManager: failed to load %s topics: %s", channel, exc)
            return self._cache.get(channel, {})

    def _invalidate_cache(self, channel: str) -> None:
        self._cache.pop(channel, None)
        self._cache_ts.pop(channel, None)
