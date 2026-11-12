"""[INPUT]
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Business-layer adapter connecting /background (/btw /bg) slash commands to the persistent Kanban task system.)
- app.core.channel_bridge.btw_notifier::BtwTaskNotifier (POS: Business-layer ServerEventBus subscriber. Does NOT modify the Kanban pipeline, dispatcher callbacks, or NotificationDispatcher.)
- app.core.channel_bridge.goal_terminal_notifier::GoalTerminalNotifier (POS: Business-layer ServerEventBus subscriber. Mirrors BtwTaskNotifier pattern for Goal lifecycle — does NOT modify the Goal pipeline, dispatcher, or harness layer.)
- app.core.channel_bridge.kanban_command_handler::ChannelKanbanCommandHandler (POS: Business-layer adapter connecting /kanban (/kb) slash commands to the KanbanService.)
- app.core.channel_bridge.webui_voice_work_notifier::WebuiVoiceWorkNotifier (POS: Server business layer. Closes the WebUI loop when BtwTaskNotifier skips web chats.)
- app.core.notifications.dispatcher::NotificationDispatcher (POS: Decoupled notification layer. Does NOT modify pairing_store, SSE endpoint, or ServerEventBus — only adds a new subscriber alongside the existing SSE consumer.)
- app.core.web_push.dispatcher::WebPushDispatcher (POS: Independent ServerEventBus subscriber. Does NOT modify dispatcher.py or btw_notifier.py.)

[OUTPUT]
- （仅导出常量/类型）

[POS]
gateway 与 instances 共享的运行时单例；集中一处，保证读写同一对象。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier
    from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier
    from app.core.channel_bridge.kanban_command_handler import ChannelKanbanCommandHandler
    from app.core.channel_bridge.webui_voice_work_notifier import WebuiVoiceWorkNotifier
    from app.core.notifications.dispatcher import NotificationDispatcher
    from app.core.web_push.dispatcher import WebPushDispatcher

_notification_dispatcher: "NotificationDispatcher | None" = None
_btw_notifier: "BtwTaskNotifier | None" = None
_webui_voice_work_notifier: "WebuiVoiceWorkNotifier | None" = None
_goal_terminal_notifier: "GoalTerminalNotifier | None" = None
_web_push_dispatcher: "WebPushDispatcher | None" = None
_background_task_handler: "ChannelBackgroundTaskHandler | None" = None
_kanban_command_handler: "ChannelKanbanCommandHandler | None" = None
