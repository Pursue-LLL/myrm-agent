"""Per-command environment of a persistent shell.

A persistent shell is created once and lives across many commands, so an environment given only at creation is
frozen for its whole life. These tests drive real shells: a ``scoped`` variable (a credential) exists for exactly
the command it was given to, a ``sticky`` one is refreshed on every command and stays for the later ones.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession, SessionConfig
from myrm_agent_harness.toolkits.code_execution.session.models import CommandEnv
from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import (
    BashFlavor,
    PowerShellFlavor,
    ShellFlavor,
    WindowsFlavor,
)

_TRICKY = "a\"b\\c d$HOME `whoami` $(echo pwned) 'q'\nsecond-line"

needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="drives a real bash shell")


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[LocalPersistentSession]:
    config = SessionConfig(session_id="command-env", work_dir=str(tmp_path), timeout=20, sandbox_mode="disable")
    shell = LocalPersistentSession(config)
    await shell.start()
    try:
        yield shell
    finally:
        await shell.close()


async def _read(session: LocalPersistentSession, name: str, env: CommandEnv | None = None) -> str:
    result = await session.execute(f"printf '%s' \"${{{name}-<unset>}}\"", env=env)
    assert result.success
    return result.stdout


@needs_bash
class TestScopedEnv:
    async def test_scoped_value_reaches_its_command_only(self, session: LocalPersistentSession) -> None:
        env = CommandEnv(scoped={"TOKEN_A": "secret-1"})

        assert await _read(session, "TOKEN_A", env) == "secret-1"
        assert await _read(session, "TOKEN_A") == "<unset>"

    async def test_scoped_value_reaches_a_shell_that_is_already_running(self, session: LocalPersistentSession) -> None:
        assert await _read(session, "TOKEN_A") == "<unset>"

        assert await _read(session, "TOKEN_A", CommandEnv(scoped={"TOKEN_A": "late"})) == "late"

    async def test_each_command_sees_only_its_own_scoped_value(self, session: LocalPersistentSession) -> None:
        await _read(session, "TOKEN_A", CommandEnv(scoped={"TOKEN_A": "first"}))

        assert await _read(session, "TOKEN_A", CommandEnv(scoped={"TOKEN_A": "second"})) == "second"
        assert await _read(session, "TOKEN_A", CommandEnv(scoped={})) == "<unset>"

    async def test_value_stays_literal(self, session: LocalPersistentSession) -> None:
        assert await _read(session, "TOKEN_A", CommandEnv(scoped={"TOKEN_A": _TRICKY})) == _TRICKY

    async def test_scoped_value_is_removed_after_a_failing_command(self, session: LocalPersistentSession) -> None:
        result = await session.execute("false", env=CommandEnv(scoped={"TOKEN_A": "secret"}))
        assert result.exit_code == 1

        assert await _read(session, "TOKEN_A") == "<unset>"

    async def test_scoped_value_is_removed_after_exit_n(self, session: LocalPersistentSession) -> None:
        result = await session.execute("exit 3", env=CommandEnv(scoped={"TOKEN_A": "secret"}))
        assert result.exit_code == 3

        assert await _read(session, "TOKEN_A") == "<unset>"

    async def test_scoped_value_is_removed_after_a_stream(self, session: LocalPersistentSession) -> None:
        chunks = [
            chunk
            async for chunk in session.execute_stream(
                "printf '%s' \"$TOKEN_A\"", env=CommandEnv(scoped={"TOKEN_A": "streamed"})
            )
        ]

        assert "streamed" in "".join(chunks)
        assert await _read(session, "TOKEN_A") == "<unset>"

    async def test_shell_state_the_command_made_is_kept(self, session: LocalPersistentSession) -> None:
        await session.execute("export KEPT=yes && cd /", env=CommandEnv(scoped={"TOKEN_A": "x"}))

        assert await _read(session, "KEPT") == "yes"
        assert (await session.execute("pwd")).stdout.strip() == "/"


@needs_bash
class TestStickyEnv:
    async def test_sticky_value_is_refreshed_on_every_command(self, session: LocalPersistentSession) -> None:
        assert await _read(session, "ORG", CommandEnv(sticky={"ORG": "one"})) == "one"
        assert await _read(session, "ORG", CommandEnv(sticky={"ORG": "two"})) == "two"

    async def test_sticky_value_stays_for_later_commands(self, session: LocalPersistentSession) -> None:
        await _read(session, "ORG", CommandEnv(sticky={"ORG": "kept"}))

        assert await _read(session, "ORG") == "kept"


class TestWrappedCommand:
    def test_without_env_the_wrapper_is_unchanged(self) -> None:
        flavor = BashFlavor()

        assert flavor.build_wrapped_command("echo hi", "EX", "END", "$?") == flavor.build_wrapped_command(
            "echo hi", "EX", "END", "$?", CommandEnv()
        )

    def test_bash_exports_inside_the_block_and_unsets_after_the_end_marker(self) -> None:
        wrapped = BashFlavor().build_wrapped_command(
            "echo hi", "EX", "END", "$?", CommandEnv(sticky={"ORG": "o"}, scoped={"TOKEN_A": "t"})
        )

        lines = wrapped.splitlines()
        block = lines[lines.index("{") + 1 : lines.index("}")]
        assert block == ["export ORG=$'o'", "export TOKEN_A=$'t'", "echo hi", "__myrm_rc__=$?"]
        assert lines[-1] == "unset TOKEN_A"
        assert lines.index("echo 'END'") == len(lines) - 2

    def test_powershell_sets_before_the_block_and_removes_after_the_end_marker(self) -> None:
        wrapped = PowerShellFlavor().build_wrapped_command(
            "Get-Date", "EX", "END", "$LASTEXITCODE", CommandEnv(scoped={"TOKEN_A": "t"})
        )

        lines = wrapped.splitlines()
        assert lines[0] == "$env:TOKEN_A = 't'"
        assert lines[1] == "& {"
        assert lines[-1] == "Remove-Item Env:TOKEN_A -ErrorAction SilentlyContinue"

    def test_windows_cmd_sets_before_the_command_and_clears_after_the_end_marker(self) -> None:
        wrapped = WindowsFlavor().build_wrapped_command(
            "dir", "EX", "END", "%errorlevel%", CommandEnv(scoped={"TOKEN_A": "t"})
        )

        lines = wrapped.splitlines()
        assert lines[0] == "set TOKEN_A=t"
        assert lines[1] == "dir"
        assert lines[-1] == "set TOKEN_A="

    def test_powershell_value_is_always_a_quoted_literal(self) -> None:
        flavor = PowerShellFlavor()

        assert flavor.format_env_set("K", "abc-123") == "$env:K = 'abc-123'"
        assert flavor.format_env_set("K", "a\u2019b'c") == "$env:K = 'a\u2019\u2019b''c'"

    @pytest.mark.parametrize("flavor", [BashFlavor(), PowerShellFlavor(), WindowsFlavor()])
    def test_a_name_that_is_not_a_plain_identifier_is_never_emitted(self, flavor: ShellFlavor) -> None:
        wrapped = flavor.build_wrapped_command(
            "echo hi", "EX", "END", "$?", CommandEnv(scoped={"BAD NAME; rm -rf /": "x", "GOOD_NAME": "y"})
        )

        assert "rm -rf" not in wrapped
        assert "GOOD_NAME" in wrapped
