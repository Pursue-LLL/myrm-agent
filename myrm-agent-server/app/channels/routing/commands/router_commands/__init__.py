"""Router 命令 mixin 门面：按命令族组合。

[OUTPUT]
各命令族 mixin（审批、审批收尾、委派、草稿、目标、记忆、模式、配额、会话、停止）、由它们组合出的 RouterCommandsMixin、DraftAction / parse_draft_args

[POS]
`app.channels.routing.commands.router_commands` 的唯一入口；每个命令族的实现在同目录单独模块中。
"""

from app.channels.routing.commands.router_commands.approval import RouterCommandsApprovalMixin
from app.channels.routing.commands.router_commands.approval_end import RouterCommandsApprovalEndMixin
from app.channels.routing.commands.router_commands.delegation import RouterCommandsDelegationMixin
from app.channels.routing.commands.router_commands.draft import (
    DraftAction,
    RouterCommandsDraftMixin,
    parse_draft_args,
)
from app.channels.routing.commands.router_commands.goals import RouterCommandsGoalsMixin
from app.channels.routing.commands.router_commands.memory import RouterCommandsMemoryMixin
from app.channels.routing.commands.router_commands.mixin import RouterCommandsMixin
from app.channels.routing.commands.router_commands.modes import RouterCommandsModesMixin
from app.channels.routing.commands.router_commands.quota import RouterCommandsQuotaMixin
from app.channels.routing.commands.router_commands.session import RouterCommandsSessionMixin
from app.channels.routing.commands.router_commands.stop import RouterCommandsStopMixin

__all__ = [
    "DraftAction",
    "RouterCommandsApprovalEndMixin",
    "RouterCommandsApprovalMixin",
    "RouterCommandsDelegationMixin",
    "RouterCommandsDraftMixin",
    "RouterCommandsGoalsMixin",
    "RouterCommandsMemoryMixin",
    "RouterCommandsMixin",
    "RouterCommandsModesMixin",
    "RouterCommandsQuotaMixin",
    "RouterCommandsSessionMixin",
    "RouterCommandsStopMixin",
    "parse_draft_args",
]
