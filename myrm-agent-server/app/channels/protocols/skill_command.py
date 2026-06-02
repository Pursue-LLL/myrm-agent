"""Skill command handler protocol — business-layer injection for /skill commands.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- SkillCommandHandler: Protocol for resolving and invoking skill-bound slash commands

[POS]
Business-layer handler protocol for skill-bound slash commands. When a user
sends a /command that is bound to a Skill (via AgentProfile.command_bindings),
the framework delegates to this handler. The business layer loads the Skill
content and injects it as the user message, bypassing LLM skill selection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.channels.types import InboundMessage


@runtime_checkable
class SkillCommandHandler(Protocol):
    """Protocol for handling skill-bound slash commands.

    Implemented by the business layer (myrm-agent-server). The framework
    calls this when a user sends a /command that resolves to a Skill binding.
    The handler should load the Skill content and return a modified
    InboundMessage with the Skill invocation injected as the message content.
    """

    async def __call__(
        self,
        msg: InboundMessage,
        skill_id: str,
        user_args: str,
    ) -> InboundMessage | None:
        """Build an InboundMessage with Skill content injected.

        Args:
            msg: Original inbound message that triggered the command.
            skill_id: The Skill ID to invoke (from CommandDef.skill_id).
            user_args: Trailing text the user typed after the command.

        Returns:
            A new InboundMessage with Skill invocation content set as
            msg.content, ready for agent execution. Returns None if the
            Skill could not be loaded (framework will send an error reply).
        """
        ...
