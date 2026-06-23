"""Goal command handler protocol — business-layer injection for /goal commands.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- GoalCommandHandler: Protocol for handling /goal slash commands

[POS]
Business-layer handler protocol for the /goal slash command. The framework
parses subcommands and delegates execution to this handler. The business layer
connects to the GoalManager/GoalProvider to execute goal lifecycle operations.
"""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@unique
class GoalSubcommand(StrEnum):
    """Parsed /goal subcommand actions."""

    SET = "set"
    STATUS = "status"
    PAUSE = "pause"
    RESUME = "resume"
    CLEAR = "clear"
    BUDGET = "budget"
    CONSTRAINT = "constraint"


@unique
class SubgoalSubcommand(StrEnum):
    """Parsed /subgoal subcommand actions."""

    ADD = "add"
    LIST = "list"
    REMOVE = "remove"
    CLEAR = "clear"


@runtime_checkable
class GoalCommandHandler(Protocol):
    """Protocol for handling /goal and /subgoal slash commands.

    Implemented by the business layer (myrm-agent-server). The framework
    calls this when a user sends /goal or /subgoal with a parsed subcommand.
    """

    async def handle_goal(
        self,
        msg: InboundMessage,
        subcommand: GoalSubcommand,
        args: str,
    ) -> str:
        """Execute a /goal subcommand and return a user-visible response."""
        ...

    async def handle_subgoal(
        self,
        msg: InboundMessage,
        subcommand: SubgoalSubcommand,
        args: str,
    ) -> str:
        """Execute a /subgoal subcommand and return a user-visible response."""
        ...

    async def get_kickoff_message(
        self,
        msg: InboundMessage,
        goal_text: str,
    ) -> InboundMessage | None:
        """Build a kickoff message to start agent work on the new goal.

        Called after a successful SET operation. Returns an InboundMessage
        with the goal text as content, ready to be submitted to SessionGate
        for immediate agent execution. Returns None to skip auto-kickoff.

        Args:
            msg: Original /goal command message.
            goal_text: The goal objective text.

        Returns:
            InboundMessage for agent execution, or None to skip kickoff.
        """
        ...
