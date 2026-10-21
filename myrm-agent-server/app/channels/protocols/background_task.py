"""Background task handler protocol — business-layer injection for /background commands.

[INPUT]
- channels.types::InboundMessage (POS: Channel inbound message data model)

[OUTPUT]
- BackgroundTaskInfo: Frozen dataclass describing an active or completed background task.
- BackgroundTaskHandler: Protocol for handling /background (/btw /bg) slash commands.

[POS]
Business-layer handler protocol for the /background slash command. The framework
parses subcommands (spawn / list / cancel / steer) and delegates execution to this
handler. The business layer spawns independent subagent sessions, manages their
lifecycle, persists results, and pushes completion notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@dataclass(frozen=True, slots=True)
class BackgroundTaskInfo:
    """Snapshot of a background task's state for list display."""

    task_id: str
    prompt: str
    status: str  # "running" | "completed" | "failed" | "timed_out" | "cancelled"
    created_at: float
    completed_at: float | None = None
    result_preview: str | None = None


@runtime_checkable
class BackgroundTaskHandler(Protocol):
    """Protocol for handling /background (/btw /bg) slash commands.

    Implemented by the business layer (myrm-agent-server). The framework
    calls this when a user sends /background with a parsed subcommand.
    The handler manages independent background agent sessions.
    """

    async def spawn_background(
        self,
        msg: InboundMessage,
        prompt: str,
    ) -> str:
        """Spawn a new background task and return its task_id.

        Args:
            msg: Original inbound message (provides user_id, channel, chat_id context).
            prompt: The task description to execute in the background.

        Returns:
            Generated task_id string for the background task.
        """
        ...

    async def cancel_background(
        self,
        msg: InboundMessage,
        task_id: str,
    ) -> bool:
        """Cancel a running background task.

        Args:
            msg: Original inbound message (for authorization context).
            task_id: ID of the background task to cancel.

        Returns:
            True if the task was found and cancellation was initiated.
        """
        ...

    async def list_background(
        self,
        msg: InboundMessage,
    ) -> list[BackgroundTaskInfo]:
        """List all background tasks for the current user/session.

        Args:
            msg: Original inbound message (provides user_id context).

        Returns:
            List of background task info snapshots.
        """
        ...

    async def steer_background(
        self,
        msg: InboundMessage,
        task_id: str,
        instruction: str,
    ) -> bool:
        """Inject a steering instruction into a running background task.

        Args:
            msg: Original inbound message (for authorization context).
            task_id: ID of the background task to steer.
            instruction: New instruction to inject.

        Returns:
            True if the task was found and steering was applied.
        """
        ...
