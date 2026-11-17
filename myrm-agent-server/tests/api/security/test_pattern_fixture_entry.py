"""The allowlist pattern fixture seeds an entry the permission engine matches."""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID, Allowlist, AllowlistEntry
from myrm_agent_harness.agent.security.tool_registry import resolve_permission_type

from app.api.security import test_fixtures


@pytest.mark.parametrize(
    ("command", "covered"),
    [("npm install left-pad", True), ("rm -rf build", False)],
    ids=["a-command-of-the-pattern", "another-command"],
)
async def test_the_seeded_entry_covers_the_bash_tool_commands_of_its_pattern(command: str, covered: bool) -> None:
    allowlist = Allowlist()
    await allowlist.add(
        DEFAULT_USER_ID,
        AllowlistEntry(
            permission=test_fixtures._PATTERN_PERMISSION,
            tool_name=test_fixtures._PATTERN_TOOL,
            command_pattern=test_fixtures._PATTERN_COMMAND,
        ),
    )
    tool = test_fixtures._PATTERN_TOOL

    found = allowlist.check(DEFAULT_USER_ID, resolve_permission_type(tool, {"command": command}), tool, command=command)

    assert found is covered
