"""Learn command handler protocol — business-layer injection for /learn command.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- LearnCommandHandler: Protocol for handling /learn slash commands

[POS]
Business-layer handler protocol for the /learn slash command. The framework
extracts user_args from the command and delegates to this handler. The handler
builds a learn prompt and returns a modified InboundMessage with the prompt
injected, ready for agent execution via SessionGate. Returns None to skip
(framework sends usage hint).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@runtime_checkable
class LearnCommandHandler(Protocol):
    """Protocol for handling the /learn slash command.

    Implemented by the business layer (myrm-agent-server). The framework
    calls this when a user sends /learn with trailing arguments. The handler
    builds a learn prompt incorporating the user's request, current agent
    context, and skill-authoring standards, then returns a modified
    InboundMessage ready for agent execution.
    """

    async def __call__(
        self,
        msg: InboundMessage,
        user_args: str,
    ) -> InboundMessage | None:
        """Build an InboundMessage with the learn prompt injected.

        Args:
            msg: Original inbound message that triggered /learn.
            user_args: Trailing text the user typed after /learn
                       (URL, file path, or free-text description).

        Returns:
            A new InboundMessage with learn prompt as content, ready for
            agent execution. Returns None if the request cannot be processed.
        """
        ...
