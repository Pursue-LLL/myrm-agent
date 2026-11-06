"""[INPUT]
- app.config.deploy_mode::is_local_mode (POS: 部署模式与运行方式)
- app.core.channel_bridge::channel_gateway (POS: Application-level channel gateway singleton.)
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Business-layer adapter connecting /background (/btw /bg) slash commands to the)
- app.core.channel_bridge.btw_notifier::BtwTaskNotifier (POS: Business-layer ServerEventBus subscriber. Does NOT modify the Kanban pipeline,)
- app.core.channel_bridge.channel_factory::create_all_channels (POS: Business-layer assembly. Bridges framework channel factory with)
- app.core.channel_bridge.goal_terminal_notifier::GoalTerminalNotifier (POS: Business-layer ServerEventBus subscriber. Mirrors BtwTaskNotifier pattern for)
- app.core.channel_bridge.setup.callbacks::_on_channel_status_change / _on_connection_change / _on_groups_change (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)
- app.core.channel_bridge.setup.instances::_enable_core_router / _restore_channel_instances (POS: channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。)
- app.core.channel_bridge.wake_return::clear_wake_im_ports / register_wake_im_ports (POS: Package entry for the IM half of a wake turn: whether the member is mid-conversation, and where its reply goes.)
- app.core.channel_bridge.webui_voice_work_notifier::WebuiVoiceWorkNotifier (POS: Server business layer. Closes the WebUI loop when BtwTaskNotifier skips web chats.)
- app.core.notifications.dispatcher::NotificationDispatcher (POS: Decoupled notification layer. Does NOT modify pairing_store, SSE endpoint,)
- app.core.web_push.dispatcher::WebPushDispatcher (POS: Independent ServerEventBus subscriber. Does NOT modify dispatcher.py or btw_notifier.py.)
- app.core.channel_bridge.setup::state (POS: `app.core.channel_bridge.setup` 的唯一入口；实现按 gateway/instances/policies/callbacks/commands 分层。)

[OUTPUT]
- get_background_task_handler: Get the active background task handler instance.
- start_channel_gateway: Register all Channel Providers and start the Gateway.
- stop_channel_gateway: Stop the Channel Gateway.

[POS]
channel_bridge setup 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config.deploy_mode import is_local_mode
from app.core.channel_bridge import channel_gateway
from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler
from app.core.channel_bridge.btw_notifier import BtwTaskNotifier
from app.core.channel_bridge.channel_factory import create_all_channels
from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier
from app.core.channel_bridge.setup.callbacks import _on_channel_status_change, _on_connection_change, _on_groups_change
from app.core.channel_bridge.setup.instances import _enable_core_router, _restore_channel_instances
from app.core.channel_bridge.wake_return import clear_wake_im_ports, register_wake_im_ports
from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier
from app.core.notifications.dispatcher import NotificationDispatcher
from app.core.web_push.dispatcher import WebPushDispatcher

from . import state

logger = logging.getLogger(__name__)



if TYPE_CHECKING:
    pass


def get_background_task_handler() -> ChannelBackgroundTaskHandler | None:
    """Get the active background task handler instance."""
    return state._background_task_handler


async def start_channel_gateway() -> None:
    """Register all Channel Providers and start the Gateway."""
    async for channel in create_all_channels():
        channel_gateway.register(channel)

    await _enable_core_router()
    register_wake_im_ports(channel_gateway)

    from app.services.event.app_event_bus import get_event_bus

    channel_gateway.set_status_change_callback(_on_channel_status_change)
    channel_gateway.set_groups_change_callback(_on_groups_change)
    channel_gateway.set_connection_change_callback(_on_connection_change)

    await channel_gateway.start()
    mode = "bidirectional-local" if is_local_mode() else "bidirectional-cp"
    logger.info("Channel Gateway started (%s)", mode)

    await _restore_channel_instances()

    bus = get_event_bus()
    state._notification_dispatcher = NotificationDispatcher(bus)
    await state._notification_dispatcher.start()
    state._btw_notifier = BtwTaskNotifier(bus)
    await state._btw_notifier.start()
    state._webui_voice_work_notifier = WebuiVoiceWorkNotifier(bus)
    await state._webui_voice_work_notifier.start()
    state._goal_terminal_notifier = GoalTerminalNotifier(bus)
    await state._goal_terminal_notifier.start()
    state._web_push_dispatcher = WebPushDispatcher(bus)
    await state._web_push_dispatcher.start()


async def stop_channel_gateway() -> None:
    """Stop the Channel Gateway."""
    if state._web_push_dispatcher:
        try:
            await state._web_push_dispatcher.stop()
        except Exception as exc:
            logger.warning("Failed to stop web push dispatcher: %s", exc)
        finally:
            state._web_push_dispatcher = None
    if state._goal_terminal_notifier:
        try:
            await state._goal_terminal_notifier.stop()
        except Exception as exc:
            logger.warning("Failed to stop goal terminal notifier: %s", exc)
        finally:
            state._goal_terminal_notifier = None
    if state._btw_notifier:
        try:
            await state._btw_notifier.stop()
        except Exception as e:
            logger.warning("Failed to stop btw notifier: %s", e)
        finally:
            state._btw_notifier = None
    if state._webui_voice_work_notifier:
        try:
            await state._webui_voice_work_notifier.stop()
        except Exception as exc:
            logger.warning("Failed to stop webui voice work notifier: %s", exc)
        finally:
            state._webui_voice_work_notifier = None
    if state._notification_dispatcher:
        try:
            await state._notification_dispatcher.stop()
        except Exception as e:
            logger.warning("Failed to stop notification dispatcher: %s", e)
        finally:
            state._notification_dispatcher = None

    clear_wake_im_ports()

    try:
        await channel_gateway.stop()
        logger.info("Channel Gateway stopped")
    except Exception as e:
        logger.warning("Failed to stop channel gateway: %s", e)
