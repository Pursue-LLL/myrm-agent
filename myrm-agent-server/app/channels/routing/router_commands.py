"""Inbound control commands: /stop, approvals, /new, /compact, /retry, /undo, /goal, /steer, /queue, /memory, /learn, topic commands.

[INPUT]
- channels.routing.router_commands_approval::RouterCommandsApprovalMixin
- channels.routing.router_commands_session::RouterCommandsSessionMixin
- channels.routing.router_commands_modes::RouterCommandsModesMixin
- channels.routing.router_commands_goals::RouterCommandsGoalsMixin
- channels.routing.router_commands_memory::RouterCommandsMemoryMixin

[OUTPUT]
- RouterCommandsMixin: composed mixin providing all slash command handler methods for AgentRouter

[POS]
RouterCommandsMixin composed into AgentRouter (router.py) via multiple inheritance;
methods constrain self via RouterCommandsHost. Task/approval session keys use
router_keys.routing_session_key. Logger name is consistent with the router package.
"""

from __future__ import annotations

from app.channels.routing.router_commands_approval import RouterCommandsApprovalMixin
from app.channels.routing.router_commands_goals import RouterCommandsGoalsMixin
from app.channels.routing.router_commands_memory import RouterCommandsMemoryMixin
from app.channels.routing.router_commands_modes import RouterCommandsModesMixin
from app.channels.routing.router_commands_session import RouterCommandsSessionMixin


class RouterCommandsMixin(
    RouterCommandsApprovalMixin,
    RouterCommandsSessionMixin,
    RouterCommandsModesMixin,
    RouterCommandsGoalsMixin,
    RouterCommandsMemoryMixin,
):
    """Mixin: task cancellation and slash-command handlers from the consume loop."""
