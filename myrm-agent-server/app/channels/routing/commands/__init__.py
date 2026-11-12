"""Inbound slash-command domain: parsing + high-level handlers + RouterCommandsMixin composition.

[INPUT]
- ``app.channels.types`` InboundMessage/OutboundMessage (POS: message envelopes)
- ``app.channels.routing.router_keys`` routing_session_key (POS: /new session marker)
- ``app.channels.i18n`` get_text (POS: channel-facing copy)

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``commands`` subpackage:
  - commands: argument parsers (yolo/personality/memory/approval/topic) + slash-command
    handlers (new_session/compact/retry/undo/topic_command) + DenyWithReason/TopicCommand DTOs
  - router_commands.mixin: RouterCommandsMixin composed from the feature mixins below
  - router_commands.approval: RouterCommandsApprovalMixin (emoji/button/reaction approval)
  - router_commands.draft: RouterCommandsDraftMixin + parse_draft_args (/draft: decide a held reply from chat)
  - router_commands.goals: RouterCommandsGoalsMixin (/goal lifecycle)
  - router_commands.memory: RouterCommandsMemoryMixin (/memory review)
  - router_commands.modes: RouterCommandsModesMixin (/yolo, /personality, /topic)
  - router_commands.quota: RouterCommandsQuotaMixin (/quota)
  - router_commands.session: RouterCommandsSessionMixin (/new, /compact, /retry, /undo)
  - router_commands.stop: RouterCommandsStopMixin (/stop and the session abort shared with /new)

[POS]
Server business layer. Single command domain for AgentRouter: parsing and handling
stay co-located so every slash command has exactly one home. AgentRouter (router.py)
consumes this facade; tests import via this facade as well.
"""

from app.channels.routing.commands.parsers import (
    ApprovalDecision,
    DenyWithReason,
    MemoryAction,
    is_explicit_approval_command,
    normalize_approval_emoji,
    parse_approval_command,
    parse_memory_args,
    parse_personality_args,
    parse_yolo_args,
)
from app.channels.routing.commands.router_commands import (
    DraftAction,
    RouterCommandsApprovalMixin,
    RouterCommandsDraftMixin,
    RouterCommandsGoalsMixin,
    RouterCommandsMemoryMixin,
    RouterCommandsMixin,
    RouterCommandsModesMixin,
    RouterCommandsQuotaMixin,
    RouterCommandsSessionMixin,
    RouterCommandsStopMixin,
    parse_draft_args,
)
from app.channels.routing.commands.session import handle_compact, handle_new_session
from app.channels.routing.commands.topic import TopicCommand, handle_topic_command, parse_topic_args
from app.channels.routing.commands.turns import handle_retry, handle_undo

__all__ = [
    "ApprovalDecision",
    "DenyWithReason",
    "DraftAction",
    "MemoryAction",
    "RouterCommandsApprovalMixin",
    "RouterCommandsDraftMixin",
    "RouterCommandsGoalsMixin",
    "RouterCommandsMemoryMixin",
    "RouterCommandsMixin",
    "RouterCommandsModesMixin",
    "RouterCommandsQuotaMixin",
    "RouterCommandsSessionMixin",
    "RouterCommandsStopMixin",
    "TopicCommand",
    "handle_compact",
    "handle_new_session",
    "handle_retry",
    "handle_topic_command",
    "handle_undo",
    "is_explicit_approval_command",
    "normalize_approval_emoji",
    "parse_approval_command",
    "parse_draft_args",
    "parse_memory_args",
    "parse_personality_args",
    "parse_topic_args",
    "parse_yolo_args",
]
