"""SkillCommandHandler — business-layer handler for skill-bound /commands.

When a user sends a slash command bound to a Skill (e.g. /daily-report),
the router delegates here. This handler rewrites the message content to
`[use skill_name] user_args`, matching the format used by the frontend
command palette.

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

    The agent execution pipeline already recognizes `[use skill_name]` as a Skill
    invocation trigger (same format the frontend uses). This handler simply rewrites
    the message content to match that convention.
    """

    async def __call__(
        self,
        msg: InboundMessage,
        skill_id: str,
        user_args: str,
    ) -> InboundMessage | None:
        """Build a message with Skill invocation injected.

        Returns a modified InboundMessage with `[use skill_id] user_args` as content,
        or None if the skill_id is invalid.
        """
        if not skill_id:
            logger.warning("SkillCommandHandler: empty skill_id for /%s", msg.content)
            return None

        content = f"[use {skill_id}] {user_args}".strip() if user_args else f"[use {skill_id}]"

        return dataclasses.replace(msg, content=content)
