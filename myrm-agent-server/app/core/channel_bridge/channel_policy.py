"""Channel policy provider — reads DM/group policies and enabled groups from user configuration.

[INPUT]
- app.database.connection::get_session
- app.database.models::UserConfig
- app.channels.protocols.pairing::DmPolicy, GroupPolicy, GroupTriggerMode

[OUTPUT]
- SqlChannelPolicyProvider: ChannelPolicyProvider 的数据库实现

[POS]
从用户配置表读取 DM/群聊访问策略、触发模式和群组启用列表，
供 AgentRouter 在处理入站消息时决定如何处理私聊和群聊消息。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from app.channels.protocols.pairing import DmPolicy, GroupPolicy, GroupTriggerMode
from app.channels.types import ReactionLevel

logger = logging.getLogger(__name__)

_DEFAULT_DM_POLICY = DmPolicy.ALLOWLIST
_DEFAULT_GROUP_POLICY = GroupPolicy.DISABLED
_DEFAULT_REACTION_LEVEL = ReactionLevel.SIMPLE
_CACHE_TTL_SECONDS = 30

_cache_store: dict[str, object] = {"data": None, "ts": 0.0}


def _cfg_mapping(data: dict[str, object], key: str) -> dict[str, object]:
    raw = data.get(key)
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    return {}


def _nested_channel_override(config: dict[str, object], channel: str) -> dict[str, object]:
    channels = _cfg_mapping(config, "channels")
    ch_raw = channels.get(channel)
    if isinstance(ch_raw, dict):
        return {str(k): v for k, v in ch_raw.items()}
    return {}


class SqlChannelPolicyProvider:
    """Reads DM and group policies from the 'channels' config key in the database.

    Caches the config for _CACHE_TTL_SECONDS to avoid per-message DB queries.
    Resolution order: channel-specific override > global default > hardcoded default.
    Uses module-level cache so all instances (and _invalidate_cache) share state.
    """

    def __init__(self) -> None:
        pass

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        config = await self._load_channels_config()
        if not config:
            return _DEFAULT_DM_POLICY

        channel_override = _nested_channel_override(config, channel)
        if "dmPolicy" in channel_override:
            return _parse_dm_policy(channel_override["dmPolicy"])

        if "dmPolicy" in config:
            return _parse_dm_policy(config["dmPolicy"])

        return _DEFAULT_DM_POLICY

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        config = await self._load_channels_config()
        if not config:
            return _DEFAULT_GROUP_POLICY

        channel_override = _nested_channel_override(config, channel)
        if "groupPolicy" in channel_override:
            return _parse_group_policy(channel_override["groupPolicy"])

        if "groupPolicy" in config:
            return _parse_group_policy(config["groupPolicy"])

        return _DEFAULT_GROUP_POLICY

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        config = await self._load_channels_config()
        if not config:
            return GroupTriggerMode.MENTION_ONLY, []

        channel_override = _nested_channel_override(config, channel)
        trigger_cfg = channel_override.get("groupTrigger") or config.get("groupTrigger")
        if not isinstance(trigger_cfg, dict):
            return GroupTriggerMode.MENTION_ONLY, []

        return _parse_trigger_config(trigger_cfg)

    async def get_reaction_level(self, channel: str) -> ReactionLevel:
        config = await self._load_channels_config()
        if not config:
            return _DEFAULT_REACTION_LEVEL

        channel_override = _nested_channel_override(config, channel)
        if "reactionLevel" in channel_override:
            return _parse_reaction_level(channel_override["reactionLevel"])

        if "reactionLevel" in config:
            return _parse_reaction_level(config["reactionLevel"])

        return _DEFAULT_REACTION_LEVEL

    async def get_enabled_groups(self) -> set[str]:
        config = await self._load_channels_config()
        if not config:
            return set()
        raw = config.get("enabledGroups")
        if not isinstance(raw, list):
            return set()
        return {str(g) for g in raw}

    async def get_guest_mode(self, channel: str) -> bool:
        if channel != "telegram":
            return False
        creds = await self._load_credential_config("telegramCredentials")
        if not creds:
            return False
        raw = creds.get("guestMode")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in ("true", "1", "yes")
        return False

    async def get_free_response_chats(self, channel: str) -> set[str]:
        config = await self._load_channels_config()
        if not config:
            return set()

        channel_override = _nested_channel_override(config, channel)
        raw = channel_override.get("freeResponseChats") or config.get("freeResponseChats")
        if not isinstance(raw, list):
            return set()
        return {str(g) for g in raw}

    async def get_default_user_id(self) -> str | None:
        from app.api.dependencies import get_deploy_identity

        return await get_deploy_identity()

    @classmethod
    def _invalidate_cache(cls) -> None:
        """Force next read to hit the database. Called after config writes."""
        _cache_store["data"] = None
        _cache_store["ts"] = 0.0

    async def _load_channels_config(self) -> dict[str, object] | None:
        now = time.monotonic()
        cached = _cache_store["data"]
        cached_ts = _cache_store["ts"]
        if cached is not None and isinstance(cached, dict) and isinstance(cached_ts, float) and (now - cached_ts) < _CACHE_TTL_SECONDS:
            return {str(k): v for k, v in cached.items()}

        from app.database.connection import get_session
        from app.database.models import UserConfig

        async with get_session() as session:
            result = await session.execute(
                select(UserConfig.config_value).where(
                    UserConfig.config_key == "channels",
                )
            )
            row = result.scalar_one_or_none()
            data = row if isinstance(row, dict) else None
            _cache_store["data"] = data
            _cache_store["ts"] = now
            return data

    async def _load_credential_config(self, config_key: str) -> dict[str, object] | None:
        from app.database.connection import get_session
        from app.database.models import UserConfig

        async with get_session() as session:
            result = await session.execute(
                select(UserConfig.config_value).where(
                    UserConfig.config_key == config_key,
                )
            )
            row = result.scalar_one_or_none()
            if isinstance(row, dict):
                return {str(k): v for k, v in row.items()}
            return None


def _parse_dm_policy(value: object) -> DmPolicy:
    try:
        return DmPolicy(str(value))
    except ValueError:
        logger.warning("Invalid dmPolicy value: %s, falling back to allowlist", value)
        return _DEFAULT_DM_POLICY


def _parse_group_policy(value: object) -> GroupPolicy:
    try:
        return GroupPolicy(str(value))
    except ValueError:
        logger.warning("Invalid groupPolicy value: %s, falling back to disabled", value)
        return _DEFAULT_GROUP_POLICY


def _parse_reaction_level(value: object) -> ReactionLevel:
    try:
        return ReactionLevel(str(value))
    except ValueError:
        logger.warning("Invalid reactionLevel value: %s, falling back to simple", value)
        return _DEFAULT_REACTION_LEVEL


def _parse_trigger_config(cfg: dict[str, object]) -> tuple[GroupTriggerMode, list[str]]:
    raw_mode = cfg.get("mode", "mention_only")
    try:
        mode = GroupTriggerMode(str(raw_mode))
    except ValueError:
        mode = GroupTriggerMode.MENTION_ONLY

    raw_prefixes = cfg.get("prefixes", [])
    prefixes = [str(p) for p in raw_prefixes] if isinstance(raw_prefixes, list) else []
    return mode, prefixes
