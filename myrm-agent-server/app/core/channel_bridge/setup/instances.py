"""核心路由启用、实例恢复与凭据加载。

[POS]
channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.channel_bridge import channel_gateway
from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler
from app.core.channel_bridge.kanban_command_handler import ChannelKanbanCommandHandler
from app.core.channel_bridge.setup.commands import _build_agent_route_commands, _load_skill_command_bindings
from app.core.channel_bridge.setup.policies import _load_reaction_policy, _load_sticker_vision_service, _load_voice_config

from . import state

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


async def _enable_core_router() -> None:
    """Enable the core AgentRouter for both local and Control Plane ingress."""
    from app.core.channel_bridge.agent_executor import ChannelAgentExecutor
    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
    from app.core.channel_bridge.compact_handler import ChannelCompactHandler
    from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
    from app.core.channel_bridge.learn_handler import ChannelLearnCommandHandler
    from app.core.channel_bridge.locale_provider import UserConfigLocaleProvider
    from app.core.channel_bridge.pairing_store import SqlPairingStore
    from app.core.channel_bridge.personality_adapter import AppPersonalityProvider
    from app.core.channel_bridge.skill_command_handler import ChannelSkillCommandHandler
    from app.core.channel_bridge.status_handler import ChannelStatusProvider
    from app.core.channel_bridge.topic_config import SqlTopicManager
    from app.core.channel_bridge.turn_handler import ChannelRetryHandler, ChannelUndoHandler

    voice_config = await _load_voice_config()
    reaction_policy = await _load_reaction_policy()
    policy_provider = SqlChannelPolicyProvider()
    sticker_vision = await _load_sticker_vision_service()
    agent_route_commands = _build_agent_route_commands()
    skill_commands = await _load_skill_command_bindings()
    state._background_task_handler = ChannelBackgroundTaskHandler()
    state._kanban_command_handler = ChannelKanbanCommandHandler()

    channel_gateway.enable_bidirectional(
        pairing_store=SqlPairingStore(),
        agent_executor=ChannelAgentExecutor(),
        policy_provider=policy_provider,
        voice_config=voice_config,
        reaction_policy=reaction_policy,
        topic_resolver=SqlTopicManager(),
        compact_handler=ChannelCompactHandler(),
        retry_handler=ChannelRetryHandler(),
        undo_handler=ChannelUndoHandler(),
        personality_provider=AppPersonalityProvider(),
        sticker_vision=sticker_vision,
        extra_commands=agent_route_commands + skill_commands,
        skill_command_handler=ChannelSkillCommandHandler(),
        goal_handler=ChannelGoalCommandHandler(),
        background_handler=state._background_task_handler,
        kanban_handler=state._kanban_command_handler,
        learn_handler=ChannelLearnCommandHandler(),
        status_provider=ChannelStatusProvider(),
        locale_provider=UserConfigLocaleProvider(),
    )


async def _restore_channel_instances() -> None:
    """Restore persisted channel instances after Gateway start."""
    from app.core.channel_bridge.channel_factory import (
        create_channel_instance,
        load_persisted_instances,
    )

    try:
        instances = await load_persisted_instances()
    except Exception:
        logger.warning("Failed to load persisted channel instances", exc_info=True)
        return

    for entry in instances:
        channel_type = entry.get("channelType", "")
        instance_id = entry.get("instanceId", "")
        display_name = entry.get("displayName") or entry.get("label", "")
        persisted_channel_name = entry.get("channelName", "")

        if not instance_id and persisted_channel_name and display_name:
            existing = channel_gateway.bus.get_channel(persisted_channel_name)
            if existing:
                existing.display_name = display_name
            continue

        if not channel_type or not instance_id:
            continue

        channel_name = f"{channel_type}_{instance_id}"
        instance_creds = await _load_instance_credentials(channel_name)

        try:
            channel = await create_channel_instance(
                channel_type=channel_type,
                instance_id=instance_id,
                credentials=instance_creds,
            )
            if display_name:
                channel.display_name = display_name
            await channel_gateway.add_channel(channel)
            logger.info("Restored channel instance: %s", channel_name)
        except Exception:
            logger.warning("Failed to restore instance %s", channel_name, exc_info=True)


async def _load_instance_credentials(channel_name: str) -> dict[str, str] | None:
    """Load instance-specific credentials from UserConfig.

    Returns raw camelCase credentials (e.g. ``clientId``) as stored; the
    channel factory maps them to constructor params via the channel's
    credential spec, so both default and instance channels stay consistent.

    Returns the credential dict if found, or None to fall back to default credentials.
    """
    from app.channels.core.credentials import channel_credentials_config_key
    from app.core.channel_bridge.channel_factory import flatten_credential_strings
    from app.core.channel_bridge.credential_spec import load_from_db

    config_key = channel_credentials_config_key(channel_name)
    raw = await load_from_db(config_key)
    if not raw:
        return None
    return flatten_credential_strings(raw)
