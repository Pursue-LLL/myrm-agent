"""Where host-side text goes relative to an explicit ``[use skill]`` invocation.

[INPUT]
- myrm_agent_harness.agent.skill_agent.skill_reference::parse_use_tag (POS: grammar of the explicit ``[use skill]`` tag)

[OUTPUT]
- decorate_behind_skill_tag: Decorate or replace a user's text while a leading ``[use skill]`` tag stays first.

[POS]
The harness recognizes an explicit skill invocation only at the very start of the user's text, so every
host step that puts something ahead of the user's words (delivery banner, reply context) or in place of
them (spilled-payload reference) has to keep the tag first, or the skill and its hooks silently stay off.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag


def decorate_behind_skill_tag(text: str, decorate: Callable[[str], str]) -> str:
    """``decorate(text)``, with a leading ``[use skill]`` tag kept in front of the decoration.

    ``decorate`` receives only what the user wrote behind the tag, so it never sees (or duplicates) the tag.
    """
    invocation = parse_use_tag(text)
    if invocation is None:
        return decorate(text)
    return "\n\n".join(part for part in (invocation.tag, decorate(invocation.text)) if part)
