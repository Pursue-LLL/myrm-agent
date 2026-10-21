"""Compact command handler protocol — business-layer injection for /compact.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- CompactHandler: Protocol for /compact command implementation
- CompactResult: Result dataclass for compaction outcome

[POS]
Business-layer handler protocol for the /compact slash command. Framework parses user_id
and invokes handler; business layer implements DB, Chat service, and compact logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage

MAX_FOCUS_TOPIC_LENGTH = 200


@dataclass(frozen=True, slots=True)
class CompactResult:
    """Outcome of a compaction attempt (framework-level type)."""

    compacted: bool
    message_count: int = 0
    tokens_saved: int = 0
    reason: str | None = None
    focus_topic: str = ""


@runtime_checkable
class CompactHandler(Protocol):
    """Protocol for handling /compact command. Implemented by the business layer.

    The framework resolves user_id via PolicyResolver before calling.
    The handler performs DB/chat/compact_service operations.
    """

    async def __call__(self, msg: InboundMessage, user_id: str, *, focus_topic: str = "") -> CompactResult:
        """Execute compaction for the given message and user.

        Args:
            msg: Inbound message that triggered /compact.
            user_id: Resolved system user ID (from PolicyResolver).
            focus_topic: Optional topic to guide summarization focus (max 200 chars).

        Returns:
            CompactResult describing the outcome.
        """
        ...
