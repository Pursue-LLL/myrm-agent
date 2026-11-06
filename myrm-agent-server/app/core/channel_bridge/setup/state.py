"""频道桥接初始化的跨模块状态。

[POS]
gateway 与 instances 共享的运行时单例；集中一处，避免拆分后各自持有副本。
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
