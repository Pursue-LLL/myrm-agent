"""Central command registry — single source of truth for all slash commands.

[INPUT]
- channels.routing.command_defs::CommandDef, CommandKind, SYSTEM_COMMANDS

[OUTPUT]
- CommandRegistry: Registry that maps command names/aliases to CommandDef
- ResolvedCommand: Parsed command with extracted arguments

[POS]
Command registration and resolution module. System commands are registered at
import-time; business-layer commands (Skill bindings, Agent aliases) are
registered at runtime via register(). Registration validates command names
and prevents system command overwriting. The registry is an instance (not a
module-level singleton) to avoid global mutable state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.channels.i18n import channel_t
from app.channels.routing.command_defs import (
    SYSTEM_COMMANDS,
    CommandDef,
    CommandKind,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    """A slash command resolved from user input.

    Attributes:
        command_def: The matched CommandDef.
        raw_args: Trailing text after the command name (empty string if none).
    """

    command_def: CommandDef
    raw_args: str


class CommandRegistry:
    """Central registry mapping slash command names and aliases to definitions.

    Thread-safe for reads; register() should be called during setup, not
    concurrently from multiple tasks.
    """

    __slots__ = ("_commands", "_lookup")

    def __init__(self) -> None:
        self._lookup: dict[str, CommandDef] = {}
        self._commands: list[CommandDef] = []
        for cmd in SYSTEM_COMMANDS:
            self.register(cmd)

    def register(self, cmd: CommandDef) -> None:
        """Register a command definition (name + all aliases).

        Raises:
            ValueError: If name is empty, contains spaces, or starts with '/'.
            ValueError: If attempting to overwrite a SYSTEM command.
        """
        canonical = cmd.name.lower()

        if not canonical or " " in canonical or canonical.startswith("/"):
            raise ValueError(
                f"Invalid command name '{cmd.name}': "
                "must be non-empty, without spaces or leading '/'"
            )

        existing = self._lookup.get(canonical)
        if existing is not None:
            if existing.kind == CommandKind.SYSTEM:
                raise ValueError(f"Cannot overwrite system command '/{canonical}'")
            logger.warning(
                "CommandRegistry: overwriting existing command '/%s' (%s -> %s)",
                canonical,
                existing.kind.value,
                cmd.kind.value,
            )
            self._commands = [c for c in self._commands if c.name.lower() != canonical]

        for alias in cmd.aliases:
            alias_lower = alias.lower()
            if not alias_lower or " " in alias_lower or alias_lower.startswith("/"):
                raise ValueError(
                    f"Invalid alias '{alias}' for command '{cmd.name}': "
                    "must be non-empty, without spaces or leading '/'"
                )
            alias_existing = self._lookup.get(alias_lower)
            if alias_existing is not None and alias_existing.kind == CommandKind.SYSTEM:
                raise ValueError(
                    f"Cannot overwrite system command alias '/{alias_lower}'"
                )

        self._lookup[canonical] = cmd
        for alias in cmd.aliases:
            self._lookup[alias.lower()] = cmd
        self._commands.append(cmd)

    def unregister(self, name: str) -> bool:
        """Remove a command by canonical name. Returns True if found."""
        canonical = name.lower()
        cmd = self._lookup.pop(canonical, None)
        if cmd is None:
            return False
        for alias in cmd.aliases:
            self._lookup.pop(alias.lower(), None)
        self._commands = [c for c in self._commands if c.name.lower() != canonical]
        return True

    def resolve(self, user_input: str) -> ResolvedCommand | None:
        """Resolve user input to a command + arguments.

        Accepts input with or without the leading slash:
          "/stop"          → ResolvedCommand(STOP, "")
          "/yolo on 3600"  → ResolvedCommand(YOLO, "on 3600")
          "/cc fix bug"    → ResolvedCommand(AGENT_ROUTE(claude), "fix bug")

        Returns None if no command matches.
        """
        text = user_input.strip()
        if not text.startswith("/"):
            return None

        body = text[1:]
        if not body:
            return None

        space_idx = body.find(" ")
        if space_idx > 0:
            cmd_name = body[:space_idx].lower()
            raw_args = body[space_idx + 1 :].strip()
        else:
            cmd_name = body.lower()
            raw_args = ""

        cmd_def = self._lookup.get(cmd_name)
        if cmd_def is None:
            return None

        if raw_args and not cmd_def.parse_args:
            return None

        return ResolvedCommand(command_def=cmd_def, raw_args=raw_args)

    def get(self, name: str) -> CommandDef | None:
        """Look up a command by canonical name or alias."""
        return self._lookup.get(name.lower())

    def all_commands(self) -> list[CommandDef]:
        """Return all registered commands (insertion order)."""
        return list(self._commands)

    def commands_by_kind(self, kind: CommandKind) -> list[CommandDef]:
        """Return commands filtered by kind."""
        return [c for c in self._commands if c.kind == kind]

    def help_lines(self, locale: str | None = None) -> list[str]:
        """Generate /help text grouped by category."""
        by_category: dict[str, list[CommandDef]] = {}
        for cmd in self._commands:
            by_category.setdefault(cmd.category, []).append(cmd)

        lines: list[str] = []
        for category in sorted(by_category):
            cat_key = f"cat_{category.replace(' ', '_')}"
            cat_label = (
                channel_t(locale, cat_key)
                if channel_t(locale, cat_key) != cat_key
                else category
            )
            lines.append(f"\n**{cat_label}**")
            for cmd in by_category[category]:
                args = f" {cmd.args_pattern}" if cmd.args_pattern else ""
                desc_key = f"cmd_{cmd.name}"
                desc = channel_t(locale, desc_key)
                if desc == desc_key:
                    desc = cmd.description
                alias_note = ""
                if cmd.aliases:
                    aliases = ", ".join("/" + a for a in cmd.aliases)
                    alias_note = channel_t(locale, "help_alias", aliases=aliases)
                lines.append(f"  `/{cmd.name}{args}` — {desc}{alias_note}")
        return lines
