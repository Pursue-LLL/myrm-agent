"""SkillCommandHandler — business-layer handler for skill-bound /commands.

When a user sends a slash command bound to one or more Skills (e.g. /daily-report),
the router delegates here. This handler rewrites the message content to
`[use s1,s2,...] [instruction: ...] user_args`, matching the multi-skill bundle
format consumed by the harness `_preload_explicit_skill()`.

[INPUT]
- app.channels.types::InboundMessage (POS: inbound message)
- app.channels.protocols.skill_command::SkillCommandHandler (POS: handler protocol)

[OUTPUT]
- ChannelSkillCommandHandler: SkillCommandHandler protocol implementation

[POS]
Business-layer adapter that resolves Skill names from slash commands and
transforms the inbound message for agent execution.
"""

from __future__ import annotations

import dataclasses
import logging

from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)


class ChannelSkillCommandHandler:
    """Resolves skill-bound slash commands by injecting `[use skill_name]` prefix.

    The agent execution pipeline recognizes `[use skill_name]` (single) and
    `[use s1,s2,s3]` (bundle) as Skill invocation triggers. This handler
    rewrites the message content to match that convention.
    """

    async def __call__(
        self,
        msg: InboundMessage,
        skill_ids: tuple[str, ...],
        user_args: str,
        instruction: str = "",
    ) -> InboundMessage | None:
        """Build a message with Skill invocation injected.

        Returns a modified InboundMessage with `[use skill_id(s)] user_args` as content,
        or None if no valid skill_ids are provided.
        """
        if not skill_ids:
            logger.warning("SkillCommandHandler: empty skill_ids for /%s", msg.content)
            return None

        names_part = ",".join(skill_ids)
        parts: list[str] = [f"[use {names_part}]"]

        if instruction:
            parts.append(f"[instruction: {instruction}]")

        if user_args:
            parts.append(user_args)

        content = " ".join(parts).strip()
        return dataclasses.replace(msg, content=content)
