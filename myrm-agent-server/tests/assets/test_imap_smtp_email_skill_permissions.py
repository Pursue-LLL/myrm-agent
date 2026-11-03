"""The imap-smtp-email skill declares the permissions that running its own script needs.

A skill that is loaded may use a tool only for a permission the user granted it, and the user is asked for a permission
when enabling the skill only if the skill's SKILL.md declares it. The live test of the agent found the skill enabled
without a question and then refused its own script: the guardrail named the missing ``code_interpreter`` permission.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/SKILL.md: the frontmatter the seed sync reads
- myrm_agent_harness tool registry: the permission each allowed tool is checked against

[OUTPUT]
- Fails when a tool in ``allowed-tools`` is checked against a permission that ``required_permissions`` does not name.

[POS]
Static contract of the prebuilt skill ``imap-smtp-email``, next to the script tests; it keeps the enable prompt and the
runtime guardrail agreeing without a model or a mail server.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.api.skills import parse_skill_frontmatter
from myrm_agent_harness.backends.skills.permission_validator import map_permission_to_skill_permission
from myrm_agent_harness.core.security.tool_registry.registry import resolve_permission_type

_SKILL_ID = "imap-smtp-email"
_SKILL_MD = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / _SKILL_ID / "SKILL.md"


def test_every_tool_the_skill_allows_has_its_permission_declared() -> None:
    frontmatter = parse_skill_frontmatter(_SKILL_MD.read_text(encoding="utf-8"), _SKILL_ID)
    allowed_tools = (frontmatter.allowed_tools or "").split()
    assert allowed_tools, "the skill declares no allowed-tools, so there is nothing to compare"

    needed = {
        permission
        for tool in allowed_tools
        if (permission := map_permission_to_skill_permission(resolve_permission_type(tool, {}))) is not None
    }

    missing = sorted(permission.value for permission in needed if permission not in frontmatter.required_permissions)
    assert not missing, f"enabling the skill never asks for {missing}, so the guardrail refuses what its allowed-tools run"
