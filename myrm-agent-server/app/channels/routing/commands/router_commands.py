"""Inbound control commands: the router's slash-command handlers, composed from one mixin per command family.

[INPUT]
- channels.routing.commands.router_commands_approval::RouterCommandsApprovalMixin (POS: reaction/button approval, resume payloads)
- channels.routing.commands.router_commands_approval_end::RouterCommandsApprovalEndMixin (POS: the ends of an open approval without an answer: timeout resume and superseded request)
- channels.routing.commands.router_commands_stop::RouterCommandsStopMixin (POS: /stop and the session abort shared with /new)
- channels.routing.commands.router_commands_session::RouterCommandsSessionMixin (POS: /new, /compact, /retry, /undo, topic commands)
- channels.routing.commands.router_commands_modes::RouterCommandsModesMixin (POS: /yolo, /personality, /steer, /queue)
- channels.routing.commands.router_commands_goals::RouterCommandsGoalsMixin (POS: /goal, /subgoal, /background, /handoff)
- channels.routing.commands.router_commands_memory::RouterCommandsMemoryMixin (POS: /status, /kanban, /learn, /memory)
- channels.routing.commands.router_commands_draft::RouterCommandsDraftMixin (POS: /draft decisions on replies held for review)
- channels.routing.commands.router_commands_delegation::RouterCommandsDelegationMixin (POS: /delegate launch and approval hand-over of delegated runs)
- channels.routing.commands.router_commands_quota::RouterCommandsQuotaMixin (POS: /quota usage inspection)

[OUTPUT]
- RouterCommandsMixin: composed mixin providing all slash command handler methods for AgentRouter

[POS]
RouterCommandsMixin composed into AgentRouter (router.py) via multiple inheritance;
methods constrain self via RouterCommandsHost. Task/approval session keys use
router_keys.routing_session_key. Logger name is consistent with the router package.
"""

from __future__ import annotations

from .router_commands_approval import RouterCommandsApprovalMixin
from .router_commands_approval_end import RouterCommandsApprovalEndMixin
from .router_commands_delegation import RouterCommandsDelegationMixin
from .router_commands_draft import RouterCommandsDraftMixin
from .router_commands_goals import RouterCommandsGoalsMixin
from .router_commands_memory import RouterCommandsMemoryMixin
from .router_commands_modes import RouterCommandsModesMixin
from .router_commands_quota import RouterCommandsQuotaMixin
from .router_commands_session import RouterCommandsSessionMixin
from .router_commands_stop import RouterCommandsStopMixin


class RouterCommandsMixin(
    RouterCommandsApprovalMixin,
    RouterCommandsApprovalEndMixin,
    RouterCommandsStopMixin,
    RouterCommandsSessionMixin,
    RouterCommandsModesMixin,
    RouterCommandsGoalsMixin,
    RouterCommandsMemoryMixin,
    RouterCommandsDraftMixin,
    RouterCommandsDelegationMixin,
    RouterCommandsQuotaMixin,
):
    """Mixin: task cancellation and slash-command handlers from the consume loop."""
