"""Turn management protocols — business-layer injection for /retry and /undo.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- RetryHandler: Protocol for /retry command implementation
- UndoHandler: Protocol for /undo command implementation
- RetryResult: Result dataclass for retry outcome
- UndoResult: Result dataclass for undo outcome

[POS]
Business-layer handler protocol for /retry and /undo slash commands.
Symmetric design with CompactHandler: framework parses user_id, business layer handles DB operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@dataclass(frozen=True, slots=True)
class RetryResult:
    """Outcome of a retry attempt (framework-level type)."""

    success: bool
    query: str = ""
    deleted_count: int = 0


@dataclass(frozen=True, slots=True)
class UndoResult:
    """Outcome of an undo attempt (framework-level type)."""

    success: bool
    deleted_count: int = 0


@runtime_checkable
class RetryHandler(Protocol):
    """Protocol for handling /retry command. Implemented by the business layer.

    The framework resolves user_id via PolicyResolver before calling.
    Returns the original user query so the router can re-execute the agent.
    """

    async def __call__(self, msg: InboundMessage, user_id: str) -> RetryResult:
        """Execute retry for the given message and user.

        Args:
            msg: Inbound message that triggered /retry.
            user_id: Resolved system user ID (from PolicyResolver).

        Returns:
            RetryResult with the original query (for re-execution) and deletion count.
        """
        ...


@runtime_checkable
class UndoHandler(Protocol):
    """Protocol for handling /undo command. Implemented by the business layer.

    The framework resolves user_id via PolicyResolver before calling.
    Deletes the entire last turn (user message + assistant responses).
    """

    async def __call__(self, msg: InboundMessage, user_id: str) -> UndoResult:
        """Execute undo for the given message and user.

        Args:
            msg: Inbound message that triggered /undo.
            user_id: Resolved system user ID (from PolicyResolver).

        Returns:
            UndoResult describing the outcome.
        """
        ...
