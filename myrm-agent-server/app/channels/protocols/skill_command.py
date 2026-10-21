"""Skill command handler protocol — business-layer injection for /skill commands.

[INPUT]
- channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- SkillCommandHandler: Protocol for resolving and invoking skill-bound slash commands

[POS]
Business-layer handler protocol for skill-bound slash commands. When a user
sends a /command bound to one or more Skills (via AgentProfile.command_bindings),
the framework delegates to this handler. Supports single skills and multi-skill
bundles with optional instruction.
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

    Supports both single-skill and multi-skill (bundle) invocation via
    ``skill_ids``.
    """

    async def __call__(
        self,
        msg: InboundMessage,
        skill_ids: tuple[str, ...],
        user_args: str,
        instruction: str = "",
    ) -> InboundMessage | None:
        """Build an InboundMessage with Skill content injected.

        Args:
            msg: Original inbound message that triggered the command.
            skill_ids: Skill IDs to invoke (single or bundle).
            user_args: Trailing text the user typed after the command.
            instruction: Ephemeral guidance for bundle execution.

        Returns:
            A new InboundMessage with Skill invocation content set as
            msg.content, ready for agent execution. Returns None if the
            Skill(s) could not be loaded (framework will send an error reply).
        """
        ...
