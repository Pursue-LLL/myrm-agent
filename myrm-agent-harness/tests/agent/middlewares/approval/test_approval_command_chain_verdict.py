"""The approval verdict reads every command of a line, whatever joins them.

``;`` joins commands the way ``&&`` does, and so do a line break, ``|`` and ``&``; a command behind ``then`` or ``do``
is still the command that runs. A standing approval of the bash tool never carries a high-risk command of such a line
past a person, and never asks about a line of read-only commands.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID, AllowlistEntry
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.workspace_trust.context import clear_workspace_trust_context

AUTO_APPROVE, ASK = "AUTO-APPROVE", "ASK"
_STANDING_ENTRY = AllowlistEntry(permission="code_interpreter", tool_name="bash_code_execute_tool")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_taint_tracker()
    approval_flow._allowlist = approval_flow.Allowlist()
    clear_workspace_trust_context()
    yield
    clear_workspace_trust_context()
    reset_taint_tracker()


async def _verdict(command: str, *, standing: bool = False) -> str:
    """The verdict of one bash tool call, optionally with a standing approval of the user for the bash tool."""
    if standing:
        await approval_flow.get_allowlist().add(DEFAULT_USER_ID, _STANDING_ENTRY)
    config = build_channel_security_config("web", local_mode=True)
    calls = [{"name": "bash_code_execute_tool", "args": {"command": command}, "id": "c1"}]
    approved, _denied, _pending = await evaluate_tool_batch(
        calls, config, False, "/tmp", "chain-verdict", {0: "h"}, None, (), None, is_interactive=True
    )
    return AUTO_APPROVE if approved else ASK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("git status", "npm publish --access public", ASK),
        ("ls", "rm -rf build", ASK),
        ("git log --oneline -5", "git status", AUTO_APPROVE),
        ("pwd", "ls -la", AUTO_APPROVE),
    ],
)
async def test_a_semicolon_chain_is_judged_like_an_and_chain(first: str, second: str, expected: str) -> None:
    assert await _verdict(f"{first}; {second}") == await _verdict(f"{first} && {second}") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build; echo done",
        "echo a;rm -rf build",
        "echo a\nrm -rf build",
        "echo a & rm -rf build",
        "cat list | rm -rf build",
        "if true; then rm -rf build; fi",
        "for f in a b; do rm -f $f; done",
        "kill -9 1234; sleep 1",
        "f() { rm -rf build; }; f",
        "case $x in a) rm -rf build;; esac",
    ],
)
async def test_a_standing_approval_does_not_carry_a_high_risk_command_of_the_line(command: str) -> None:
    assert await _verdict(command, standing=True) == ASK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "git push; echo done",
        "git push origin main;",
        "echo a;npm publish",
        "for f in a b; do npm publish; done",
        "(cd repo;git push)",
        "gh pr create --fill; true",
        "docker push img:1&&echo done",
        "case $x in a) git push;; esac",
    ],
)
async def test_a_standing_approval_does_not_carry_an_irreversible_command_of_the_line(command: str) -> None:
    assert await _verdict(command, standing=True) == ASK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "git status; git log --oneline -5",
        "git status\ngit log --oneline -5",
        "echo 'done; rm -rf build'",
        "if true; then echo yes; fi",
        "pwd; ls -la; echo done",
        "f() { ls -la; }; f",
        "case $x in a) echo yes;; esac",
    ],
)
async def test_a_standing_approval_covers_a_line_of_read_only_commands(command: str) -> None:
    assert await _verdict(command, standing=True) == AUTO_APPROVE
