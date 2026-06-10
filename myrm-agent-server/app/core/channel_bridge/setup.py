"""Channel Gateway lifecycle management.

Creates all channel instances via ``channel_factory`` and manages
Gateway start/stop. External IM provider extras remain local-only,
but the core AgentRouter is enabled in both local mode and sandbox/CP
mode so internal channel ingress can execute through the same route.

[INPUT]
- channel_factory::create_all_channels
- app.config.deploy_mode::is_local_mode

[OUTPUT]
- start_channel_gateway / stop_channel_gateway: lifecycle entry points
- refresh_reaction_policy: reload ReactionPolicy from DB into running AgentRouter

[POS]
Thin lifecycle layer. Assembly logic lives in channel_factory.py;
credential resolution in credential_spec.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config.deploy_mode import is_local_mode
from app.core.channel_bridge import channel_gateway
from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler
from app.core.channel_bridge.btw_notifier import BtwTaskNotifier
from app.core.channel_bridge.channel_factory import create_all_channels
from app.core.notifications.dispatcher import NotificationDispatcher

if TYPE_CHECKING:
    from app.channels.routing.command_defs import CommandDef
    from app.channels.routing.router_models import (
        ReactionPolicy,
    )
    from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

_notification_dispatcher: NotificationDispatcher | None = None
_btw_notifier: BtwTaskNotifier | None = None
_background_task_handler: ChannelBackgroundTaskHandler | None = None


def get_background_task_handler() -> ChannelBackgroundTaskHandler | None:
    """Get the active background task handler instance."""
    return _background_task_handler


async def start_channel_gateway() -> None:
    """Register all Channel Providers and start the Gateway."""
    async for channel in create_all_channels():
        channel_gateway.register(channel)

    await _enable_core_router()

    from app.services.event.app_event_bus import get_event_bus

    channel_gateway.set_status_change_callback(_on_channel_status_change)
    channel_gateway.set_groups_change_callback(_on_groups_change)
    channel_gateway.set_connection_change_callback(_on_connection_change)

    await channel_gateway.start()
    mode = "bidirectional-local" if is_local_mode() else "bidirectional-cp"
    logger.info("Channel Gateway started (%s)", mode)

    await _restore_channel_instances()

    bus = get_event_bus()

    global _notification_dispatcher  # noqa: PLW0603
    _notification_dispatcher = NotificationDispatcher(bus)
    await _notification_dispatcher.start()

    global _btw_notifier  # noqa: PLW0603
    _btw_notifier = BtwTaskNotifier(bus)
    await _btw_notifier.start()


async def stop_channel_gateway() -> None:
    """Stop the Channel Gateway."""
    global _btw_notifier  # noqa: PLW0603
    if _btw_notifier:
        try:
            await _btw_notifier.stop()
        except Exception as e:
            logger.warning("Failed to stop btw notifier: %s", e)
        finally:
            _btw_notifier = None

    global _notification_dispatcher  # noqa: PLW0603
    if _notification_dispatcher:
        try:
            await _notification_dispatcher.stop()
        except Exception as e:
            logger.warning("Failed to stop notification dispatcher: %s", e)
        finally:
            _notification_dispatcher = None

    try:
        await channel_gateway.stop()
        logger.info("Channel Gateway stopped")
    except Exception as e:
        logger.warning("Failed to stop channel gateway: %s", e)


async def _enable_core_router() -> None:
    """Enable the core AgentRouter for both local and Control Plane ingress."""
    from app.core.channel_bridge.agent_executor import ChannelAgentExecutor
    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider
    from app.core.channel_bridge.compact_handler import ChannelCompactHandler
    from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
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

    global _background_task_handler  # noqa: PLW0603
    _background_task_handler = ChannelBackgroundTaskHandler()

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
        background_handler=_background_task_handler,
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

    Credentials are stored in camelCase (e.g. botToken) but channel constructors
    expect snake_case (e.g. bot_token). This function converts keys accordingly.

    Returns the credential dict if found, or None to fall back to default credentials.
    """
    import re

    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import UserConfig

    creds_id = f"{channel_name}-credentials"
    try:
        async with get_session() as session:
            row = (await session.execute(select(UserConfig).where(UserConfig.id == creds_id))).scalar_one_or_none()
            if row and isinstance(row.config_value, dict):
                return {re.sub(r"([A-Z])", r"_\1", k).lower(): str(v) for k, v in row.config_value.items()}
    except Exception:
        logger.debug("No instance credentials for %s", channel_name)
    return None


async def refresh_reaction_policy() -> None:
    """Reload reaction policy from DB and apply to the running AgentRouter."""
    policy = await _load_reaction_policy()
    channel_gateway.set_reaction_policy(policy)


async def _load_reaction_policy() -> ReactionPolicy:
    """Load ReactionPolicy from the channels config."""
    from app.channels.routing.router_models import (
        ReactionPolicy,
    )
    from app.channels.types import ReactionLevel
    from app.core.channel_bridge.credential_spec import load_from_db

    _defaults = ReactionPolicy()
    try:
        creds = await load_from_db("channels")
        if not creds:
            return _defaults

        level = _defaults.level
        raw_level = creds.get("reactionLevel")
        if isinstance(raw_level, str) and raw_level in {e.value for e in ReactionLevel}:
            level = ReactionLevel(raw_level)

        processing = _defaults.processing_emoji
        raw_proc = creds.get("processingEmoji")
        if isinstance(raw_proc, str) and raw_proc.strip():
            processing = raw_proc.strip()

        completion = _defaults.completion_emoji
        raw_comp = creds.get("completionEmoji")
        if isinstance(raw_comp, str) and raw_comp.strip():
            completion = raw_comp.strip()

        failure = _defaults.failure_emoji
        raw_fail = creds.get("failureEmoji")
        if isinstance(raw_fail, str) and raw_fail.strip():
            failure = raw_fail.strip()

        return ReactionPolicy(
            level=level,
            processing_emoji=processing,
            completion_emoji=completion,
            failure_emoji=failure,
        )
    except Exception:
        return _defaults


async def _load_sticker_vision_service() -> object | None:
    """Create StickerVisionService from user's visionFallbackModel config.

    Returns None if vision fallback model is not configured.
    """
    try:
        from app.core.channel_bridge.config_loader import _load_single_config
        from app.core.channel_bridge.model_resolver import resolve_model_config

        default_model_dict = await _load_single_config("default_model")
        if not default_model_dict:
            return None

        vision_cfg = default_model_dict.get("visionFallbackModel")
        if not vision_cfg or not isinstance(vision_cfg, dict):
            return None

        provider_id = vision_cfg.get("providerId", "")
        model_name = vision_cfg.get("model", "")
        if not provider_id or not model_name:
            return None

        providers_dict_raw = await _load_single_config("providers")
        providers_dict = providers_dict_raw if isinstance(providers_dict_raw, dict) else {}

        litellm_model = f"{provider_id}/{model_name}"
        model_cfg = resolve_model_config(providers_dict, model_override=litellm_model)

        from myrm_agent_harness.agent.config.llm import LLMConfig
        from myrm_agent_harness.toolkits.vision.fallback_engine import (
            VisionFallbackEngine,
        )

        from app.channels.media.sticker_vision import (
            StickerVisionService,
        )

        llm_config = LLMConfig(
            model=model_cfg.model,
            api_key=model_cfg.api_key,
            base_url=model_cfg.base_url,
        )
        engine = VisionFallbackEngine(llm_config)
        svc = StickerVisionService(engine)
        logger.info("Sticker vision enabled: model=%s", model_cfg.model)
        return svc
    except Exception:
        logger.warning("Failed to load sticker vision service, stickers will use emoji only")
        return None


async def _load_voice_config() -> VoiceConfig | None:
    """Load VoiceConfig from the admin user's UserConfig table."""
    try:
        from app.core.channel_bridge.config_loader import load_voice_config_only
        from app.core.channel_bridge.config_parsers import extract_voice_config

        voice_dict = await load_voice_config_only()
        voice = extract_voice_config(voice_dict)
        if voice:
            logger.info("Voice config loaded: STT=%s TTS=%s", voice.stt_enabled, voice.tts_mode)
        return voice
    except Exception:
        logger.exception("Failed to load voice config")
        return None


def _on_channel_status_change(
    channel_name: str,
    old_status: object,
    new_status: object,
) -> None:
    """Publish channel status change events to SSE."""
    from app.channels.types import ChannelStatus
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if not isinstance(old_status, ChannelStatus) or not isinstance(new_status, ChannelStatus):
        return

    event_type: AppEventType | None = None
    if new_status != ChannelStatus.RUNNING and old_status == ChannelStatus.RUNNING:
        event_type = AppEventType.CHANNEL_DISCONNECTED

    if event_type:
        event = AppEvent(
            event_type=event_type,
            data={"channel": channel_name, "status": new_status.value},
        )
        get_event_bus().publish(event)
        logger.info("SSE: %s -> %s", event_type.value, channel_name)


def _on_connection_change(channel_name: str, connected: bool) -> None:
    """Publish channel connection state change events to SSE."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    event_type = AppEventType.CHANNEL_CONNECTED if connected else AppEventType.CHANNEL_DISCONNECTED
    event = AppEvent(
        event_type=event_type,
        data={
            "channel": channel_name,
            "status": "running" if connected else "disconnected",
        },
    )
    get_event_bus().publish(event)
    logger.info("SSE: %s -> %s", event_type.value, channel_name)


def _on_groups_change(channel_name: str, groups: list[object]) -> None:
    """Publish groups list update events to SSE."""
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    event = AppEvent(
        event_type=AppEventType.GROUPS_UPDATED,
        data={"channel": channel_name, "count": len(groups)},
    )
    get_event_bus().publish(event)
    logger.info("SSE: groups_updated -> %s (%d groups)", channel_name, len(groups))


def _build_agent_route_commands() -> tuple[CommandDef, ...]:
    """Build agent routing slash commands for this deployment.

    These are business-layer definitions (specific agent names/aliases)
    registered into the harness CommandRegistry at router init time.
    """
    from app.channels.routing.command_defs import (
        CommandDef,
        CommandKind,
    )

    _AGENT_ROUTES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("claude", "Route message to Claude agent", ("cc",)),
        ("codex", "Route message to Codex agent", ("cx",)),
        ("cursor", "Route message to Cursor agent", ("cs",)),
        ("kimi", "Route message to Kimi agent", ("km",)),
        ("gemini", "Route message to Gemini agent", ("gm",)),
        ("openclaw", "Route message to OpenClaw agent", ("oc",)),
        ("opencode", "Route message to OpenCode agent", ("ocd",)),
    )

    return tuple(
        CommandDef(
            name=agent_id,
            description=description,
            kind=CommandKind.AGENT_ROUTE,
            aliases=aliases,
            agent_id=agent_id,
            parse_args=True,
            category="Agent",
        )
        for agent_id, description, aliases in _AGENT_ROUTES
    )


async def _load_skill_command_bindings() -> tuple[CommandDef, ...]:
    """Load skill command bindings from all agent profiles.

    Reads AgentProfile.command_bindings from the DB and converts each
    CommandBinding to a CommandDef(kind=SKILL) for registration in the
    CommandRegistry.

    Returns an empty tuple if no bindings exist or on any error.
    """
    from app.channels.routing.command_defs import (
        CommandDef,
        CommandKind,
    )

    try:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models import Agent

        async with get_session() as session:
            result = await session.execute(select(Agent))
            agents = result.scalars().all()

        if not agents:
            return ()

        from app.database.repositories.agent_repo import AgentRepository

        commands: list[CommandDef] = []
        for agent in agents:
            profile = AgentRepository._agent_to_profile(agent)
            if not profile.command_bindings:
                continue
            for binding in profile.command_bindings:
                commands.append(
                    CommandDef(
                        name=binding.command_name,
                        description=binding.description or f"Invoke skill: {binding.skill_id}",
                        kind=CommandKind.SKILL,
                        aliases=binding.aliases,
                        skill_id=binding.skill_id,
                        parse_args=True,
                        category="Skill",
                    )
                )

        return tuple(commands)
    except Exception:
        logger.warning("Failed to load skill command bindings", exc_info=True)
        return ()


async def reload_skill_command_bindings() -> None:
    """Reload skill command bindings from DB and update the live CommandRegistry.

    Called when agent command_bindings change (create/update/delete).
    """
    new_commands = await _load_skill_command_bindings()
    channel_gateway.update_skill_commands(new_commands)
    logger.info(
        "Reloaded skill command bindings: %d commands registered",
        len(new_commands),
    )
