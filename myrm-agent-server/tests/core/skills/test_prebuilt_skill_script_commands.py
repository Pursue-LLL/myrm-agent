"""The script commands a prebuilt skill documents are plain calls of that skill.

A skill's saved settings (a mailbox password, a Google token) are handed to a bash command only when it is a plain call
of the skill's own script. The agent copies the commands from ``SKILL.md``, so a documented command the executor would
not recognise as plain would run without the settings the skill was configured with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.agent.skills.runtime.skill_invocation import plain_skill_call

PREBUILT_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills"
_SCRIPT_COMMAND = re.compile(r"(?:(?:python3?|bash|sh|node)\s+(?:-\w+\s+)*)?\.claude/skills/")


def _documented_script_commands() -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for skill_md in sorted(PREBUILT_ASSETS.glob("*/SKILL.md")):
        for line in skill_md.read_text(encoding="utf-8").splitlines():
            command = re.sub(r"^\$\s+", "", line.strip().strip("`"))
            if _SCRIPT_COMMAND.match(command):
                commands.append((skill_md.parent.name, command))
    return commands


def test_the_script_skills_document_commands() -> None:
    documenting = {skill for skill, _ in _documented_script_commands()}

    assert {"imap-smtp-email", "google-workspace", "x-live-search"} <= documenting


@pytest.mark.parametrize(("skill", "command"), _documented_script_commands())
def test_documented_command_is_a_plain_call_of_its_own_skill(skill: str, command: str) -> None:
    assert plain_skill_call(command) == skill
