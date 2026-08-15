"""Inbound slash-command domain: parsing + high-level handlers + RouterCommandsMixin composition.

[INPUT]
- ``app.channels.types`` InboundMessage/OutboundMessage (POS: message envelopes)
- ``app.channels.routing.router_keys`` routing_session_key (POS: /new session marker)
- ``app.channels.i18n`` get_text (POS: channel-facing copy)

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``commands`` subpackage:
  - commands: argument parsers (yolo/personality/memory/approval/topic) + slash-command
    handlers (new_session/compact/retry/undo/topic_command) + DenyWithReason/TopicCommand DTOs
  - router_commands: RouterCommandsMixin composed from the five feature mixins below
  - router_commands_approval: RouterCommandsApprovalMixin (emoji/button/reaction approval)
  - router_commands_goals: RouterCommandsGoalsMixin (/goal lifecycle)
  - router_commands_memory: RouterCommandsMemoryMixin (/memory review)
  - router_commands_modes: RouterCommandsModesMixin (/yolo, /personality, /topic)
  - router_commands_session: RouterCommandsSessionMixin (/new, /compact, /retry, /undo)

[POS]
Server business layer. Single command domain for AgentRouter: parsing and handling
stay co-located so every slash command has exactly one home. AgentRouter (router.py)
consumes this facade; tests import via this facade as well.
"""

from app.channels.routing.commands.commands import (
    ApprovalDecision,
    DenyWithReason,
    MemoryAction,
    TopicCommand,
    handle_compact,
    handle_new_session,
    handle_retry,
    handle_topic_command,
    handle_undo,
    is_explicit_approval_command,
    normalize_approval_emoji,
    parse_approval_command,
    parse_memory_args,
    parse_personality_args,
    parse_topic_args,
    parse_yolo_args,
)
from app.channels.routing.commands.router_commands import RouterCommandsMixin
from app.channels.routing.commands.router_commands_approval import RouterCommandsApprovalMixin
from app.channels.routing.commands.router_commands_goals import RouterCommandsGoalsMixin
from app.channels.routing.commands.router_commands_memory import RouterCommandsMemoryMixin
from app.channels.routing.commands.router_commands_modes import RouterCommandsModesMixin
from app.channels.routing.commands.router_commands_session import RouterCommandsSessionMixin

__all__ = [
    "ApprovalDecision",
    "DenyWithReason",
    "MemoryAction",
    "RouterCommandsApprovalMixin",
    "RouterCommandsGoalsMixin",
    "RouterCommandsMemoryMixin",
    "RouterCommandsMixin",
    "RouterCommandsModesMixin",
    "RouterCommandsSessionMixin",
    "TopicCommand",
    "handle_compact",
    "handle_new_session",
    "handle_retry",
    "handle_topic_command",
    "handle_undo",
    "is_explicit_approval_command",
    "normalize_approval_emoji",
    "parse_approval_command",
    "parse_memory_args",
    "parse_personality_args",
    "parse_topic_args",
    "parse_yolo_args",
]
