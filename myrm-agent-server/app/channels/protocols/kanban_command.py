"""Kanban command handler protocol — business-layer injection for /kanban commands.

[INPUT]
- channels.types::InboundMessage (POS: Channel inbound message data model)

[OUTPUT]
- KanbanCommandHandler: Protocol for handling /kanban slash commands.

[POS]
Business-layer handler protocol for the /kanban slash command. The framework
parses subcommands (list / show / create / comment / edit / complete / block /
unblock / archive / stats) and delegates execution to this handler. The
business layer calls KanbanService to perform the operations and formats
the response as Markdown.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@runtime_checkable
class KanbanCommandHandler(Protocol):
    """Protocol for handling /kanban slash commands.

    Implemented by the business layer (myrm-agent-server). The framework
    calls this with the parsed subcommand string; the handler dispatches
    to KanbanService and returns a formatted response string.
    """

    async def handle_kanban(
        self,
        msg: InboundMessage,
        raw_args: str,
    ) -> str:
        """Handle a /kanban subcommand and return a formatted response.

        Args:
            msg: Original inbound message (provides user_id, channel, chat_id context).
            raw_args: Everything after ``/kanban `` (e.g. ``"list"`` or ``"show t_abc"``).

        Returns:
            Formatted Markdown string to send back to the user.
        """
        ...
