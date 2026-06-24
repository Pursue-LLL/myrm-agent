"""Slash command data model and built-in system command definitions.

[INPUT]
- (none — leaf module)

[OUTPUT]
- CommandDef: Frozen dataclass describing a single slash command
- CommandAction: Enum of built-in system command action types
- SYSTEM_COMMANDS: Tuple of all built-in system CommandDef instances

[POS]
Command definition module: data structures for the command registry.
CommandDef is framework-level, business-agnostic; business-layer commands
(Skill bindings, Agent routing aliases) are registered at runtime via
CommandRegistry.register().
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique


@unique
class CommandAction(Enum):
    """Built-in system command actions dispatched by the router."""

    STOP = "stop"
    NEW_SESSION = "new"
    COMPACT = "compact"
    RETRY = "retry"
    UNDO = "undo"
    YOLO = "yolo"
    PERSONALITY = "personality"
    BIND = "bind"
    UNBIND = "unbind"
    TOPIC = "topic"
    APPROVE = "approve"
    GOAL = "goal"
    SUBGOAL = "subgoal"
    STEER = "steer"
    QUEUE = "queue"
    BACKGROUND = "background"
    HANDOFF = "handoff"
    KANBAN = "kanban"
    MEMORY = "memory"
    LEARN = "learn"
    STATUS = "status"
    HELP = "help"


@unique
class CommandKind(Enum):
    """Classification of how a command is dispatched."""

    SYSTEM = "system"
    SKILL = "skill"
    AGENT_ROUTE = "agent_route"


@dataclass(frozen=True, slots=True)
class CommandDef:
    """Definition of a single slash command.

    Attributes:
        name: Canonical name without the leading slash (e.g. "stop").
        description: Human-readable description shown in /help.
        kind: Classification for dispatch routing.
        action: Built-in action enum (only for system commands).
        aliases: Alternative names that resolve to this command.
        args_pattern: Argument placeholder for help text (e.g. "<prompt>", "[name]").
        category: Grouping label for /help display.
        skill_ids: Bound skill IDs — single or bundle (only for CommandKind.SKILL).
        instruction: Ephemeral guidance for bundles.
        agent_id: Target agent ID (only for CommandKind.AGENT_ROUTE).
        parse_args: Whether the command accepts trailing text as arguments.
    """

    name: str
    description: str
    kind: CommandKind = CommandKind.SYSTEM
    action: CommandAction | None = None
    aliases: tuple[str, ...] = ()
    args_pattern: str = ""
    category: str = "General"
    skill_ids: tuple[str, ...] = ()
    """Bound skill IDs (single or bundle)."""
    instruction: str = ""
    """Ephemeral guidance text injected alongside the SOP(s) for bundles."""
    agent_id: str | None = None
    parse_args: bool = False
    requires_admin: bool = False


SYSTEM_COMMANDS: tuple[CommandDef, ...] = (
    CommandDef(
        name="stop",
        description="Stop the currently running agent task",
        action=CommandAction.STOP,
        category="Session",
    ),
    CommandDef(
        name="new",
        description="Start a new conversation session",
        action=CommandAction.NEW_SESSION,
        category="Session",
    ),
    CommandDef(
        name="compact",
        description="Compress conversation context to reduce token cost",
        action=CommandAction.COMPACT,
        category="Session",
        parse_args=True,
        args_pattern="[focus_topic]",
    ),
    CommandDef(
        name="retry",
        description="Retry the last message",
        action=CommandAction.RETRY,
        category="Session",
    ),
    CommandDef(
        name="undo",
        description="Remove the last user/assistant exchange",
        action=CommandAction.UNDO,
        category="Session",
    ),
    CommandDef(
        name="yolo",
        description="Toggle YOLO mode (skip tool approval prompts)",
        action=CommandAction.YOLO,
        category="Configuration",
        parse_args=True,
        args_pattern="[on|off|toggle|status] [timeout_seconds]",
        requires_admin=True,
    ),
    CommandDef(
        name="personality",
        description="Switch session personality style",
        action=CommandAction.PERSONALITY,
        category="Configuration",
        parse_args=True,
        args_pattern="[style_name|list]",
    ),
    CommandDef(
        name="bind",
        description="Bind an agent to this topic or channel",
        action=CommandAction.BIND,
        category="Topic",
        parse_args=True,
        args_pattern="[agent_id]",
        requires_admin=True,
    ),
    CommandDef(
        name="unbind",
        description="Unbind agent from this topic or channel",
        action=CommandAction.UNBIND,
        category="Topic",
    ),
    CommandDef(
        name="topic",
        description="Show current topic/channel binding status",
        action=CommandAction.TOPIC,
        category="Topic",
    ),
    CommandDef(
        name="goal",
        description="Set, manage, or check a persistent cross-turn goal",
        action=CommandAction.GOAL,
        category="Goals",
        parse_args=True,
        args_pattern="<objective>|status|pause|resume|clear|budget <N>",
    ),
    CommandDef(
        name="subgoal",
        description="Dynamically add/remove/list subgoals for the running goal",
        action=CommandAction.SUBGOAL,
        category="Goals",
        parse_args=True,
        args_pattern="<text>|list|remove <n>|clear",
    ),
    CommandDef(
        name="steer",
        description="Redirect the running agent mid-execution with a new instruction",
        action=CommandAction.STEER,
        category="Execution",
        parse_args=True,
        args_pattern="<new instruction>",
    ),
    CommandDef(
        name="queue",
        description="Queue a task to run after the current agent task completes",
        action=CommandAction.QUEUE,
        category="Execution",
        parse_args=True,
        args_pattern="<task description>",
    ),
    CommandDef(
        name="background",
        description="Run a task in a separate background session without blocking the current conversation",
        action=CommandAction.BACKGROUND,
        aliases=("bg", "btw"),
        category="Execution",
        parse_args=True,
        args_pattern="<task>|list|cancel <id>|steer <id> <instruction>",
    ),
    CommandDef(
        name="handoff",
        description="Transfer this conversation to another platform/channel",
        action=CommandAction.HANDOFF,
        category="Session",
        parse_args=True,
        args_pattern="<target_channel>",
    ),
    CommandDef(
        name="kanban",
        description="Manage kanban board tasks without interrupting the agent",
        action=CommandAction.KANBAN,
        aliases=("kb",),
        category="Tasks",
        parse_args=True,
        args_pattern="list|show <id>|create <title>|comment <id> <msg>|edit <id> title|desc <text>|complete <id>|block <id> [reason]|unblock <id>|archive <id>|stats",
    ),
    CommandDef(
        name="memory",
        description="Review pending memory writes (approve/reject)",
        action=CommandAction.MEMORY,
        category="Memory",
        parse_args=True,
        args_pattern="[pending|approve <id>|reject <id>|approve all]",
    ),
    CommandDef(
        name="learn",
        description="Teach the agent a new skill from a URL, file, or conversation",
        action=CommandAction.LEARN,
        category="Skills",
        parse_args=True,
        args_pattern="<URL|path|description>",
    ),
    CommandDef(
        name="status",
        description="Show current session status (tokens, model, agent state)",
        action=CommandAction.STATUS,
        category="Info",
    ),
    CommandDef(
        name="help",
        description="Show available commands",
        action=CommandAction.HELP,
        category="Info",
    ),
)
