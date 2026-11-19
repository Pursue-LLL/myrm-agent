"""Tests for PersistentSession execution, wedge recovery, auto-restart, timeouts and process-death edge cases."""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState
from tests.toolkits.code_execution._session_helpers import make_config, state_of


class TestBasicExecution:
    @pytest.mark.asyncio
    async def test_echo(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("echo hello")
            assert result.success
            assert "hello" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        """Subshell exit code is captured correctly (bash itself stays alive)."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("(exit 42)")
            assert not result.success
            assert result.exit_code == 42
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_env_persistence(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            await session.execute("export TEST_VAR=hello123")
            result = await session.execute("echo $TEST_VAR")
            assert result.success
            assert "hello123" in result.stdout
        finally:
            await session.close()


# Shadowing ``echo`` makes the shell print the exit-code field of the wrapper as ``0x``, which is not a number.
_UNREADABLE_EXIT_CODE = 'echo() { builtin echo "$1x"; }'


class TestSessionWedgeRecovery:
    """A wedged shell (a command that never returns, or one that leaves the output boundary unreadable) must be
    killed and transparently rebuilt on the next call, not left poisoned. A command that reads stdin is no wedge:
    the command block's stdin is empty."""

    @pytest.mark.asyncio
    async def test_timeout_wedge_recovered_on_next_execute(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("sleep 30", timeout=1)
            assert not result.success
            assert result.error == "Timeout"
            assert "shell was restarted" in result.stderr
            assert session.state == SessionState.TERMINATED
            assert session.is_alive is False

            recovered = await session.execute("echo ok", timeout=5)
            assert recovered.success
            assert recovered.stdout == "ok"
            assert state_of(session) == SessionState.ACTIVE
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_a_command_that_reads_stdin_gets_end_of_file_and_the_shell_lives_on(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.process is not None
            pid = session.process.pid
            await session.execute("export KEPT=yes")

            reader = await session.execute("cat", timeout=5)
            assert reader.success
            assert reader.stdout == ""
            assert state_of(session) == SessionState.ACTIVE

            after = await session.execute("echo $KEPT", timeout=5)
            assert after.stdout == "yes"
            assert session.process.pid == pid
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_an_unreadable_exit_code_replaces_the_shell(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            poisoned = await session.execute(_UNREADABLE_EXIT_CODE, timeout=5)
            assert not poisoned.success
            assert poisoned.error == "Session corrupted"
            assert session.state == SessionState.TERMINATED

            recovered = await session.execute("echo ok", timeout=5)
            assert recovered.success
            assert recovered.stdout == "ok"
            assert state_of(session) == SessionState.ACTIVE
        finally:
            await session.close()


class TestRealUserFlow:
    """End-to-end session flow as a real user would drive it: consecutive
    commands, env persistence across rebuilds, special-char output fidelity,
    wedge recovery mid-flow, and the exit interceptor."""

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self) -> None:
        config = make_config()
        config.env = {
            "APP_TOKEN": 'sk-x"y$HOME`id`\txyz',
        }
        session = LocalPersistentSession(config)
        await session.start()
        try:
            # 1. Special-char env stays literal.
            result = await session.execute("printf '%s' \"$APP_TOKEN\"")
            assert result.success
            assert result.stdout == 'sk-x"y$HOME`id`\txyz'

            # 2. cwd + env persist across commands.
            await session.execute("mkdir -p /tmp/myrm-user-flow && cd /tmp/myrm-user-flow")
            assert (await session.execute("pwd")).stdout == "/tmp/myrm-user-flow"
            assert (await session.execute('echo "$APP_TOKEN"')).stdout == 'sk-x"y$HOME`id`\txyz'

            # 3. Multi-line output round-trips.
            result = await session.execute("printf 'a\\nb\\nc\\n'")
            assert result.success
            assert result.stdout == "a\nb\nc"

            # 4. Wedge (blocking command) kills + rebuilds; env re-injected.
            wedged = await session.execute("sleep 30", timeout=1)
            assert wedged.error == "Timeout"
            assert session.state == SessionState.TERMINATED
            result = await session.execute("printf '%s' \"$APP_TOKEN\"")
            assert result.success
            assert result.stdout == 'sk-x"y$HOME`id`\txyz'
            assert state_of(session) == SessionState.ACTIVE

            # 5. exit N is intercepted; shell survives.
            result = await session.execute("exit 3")
            assert not result.success
            assert result.exit_code == 3
            assert (await session.execute("echo final-ok")).stdout == "final-ok"
        finally:
            await session.close()


class TestAutoRestartRetry:
    @pytest.mark.asyncio
    async def test_restart_on_process_death(self) -> None:
        """When bash process dies, execute() should auto-restart and succeed."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("echo before_kill")
            assert result.success

            assert session.process is not None
            session.process.kill()
            await session.process.wait()

            result = await session.execute("echo after_kill")
            assert result.success
            assert "after_kill" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_diagnostic_returncode(self) -> None:
        """Error message from _execute_in_session contains diagnostic info."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.process is not None
            session.process.kill()
            await session.process.wait()

            result = await session._execute_core("echo x", timeout=5)
            assert not result.success
            assert result.error is not None
        finally:
            await session.close()


class TestTimeout:
    @pytest.mark.asyncio
    async def test_command_timeout(self) -> None:
        session = LocalPersistentSession(make_config(timeout=2))
        await session.start()
        try:
            result = await session.execute("sleep 30", timeout=1)
            assert not result.success
        finally:
            await session.close()


class TestCoverageEdgeCases:
    @pytest.mark.asyncio
    async def test_windows_flavor_and_properties(self) -> None:
        from myrm_agent_harness.toolkits.code_execution.platform import PlatformInfo
        from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import (
            WindowsFlavor,
        )
        from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import (
            get_flavor as _get_flavor,
        )

        pi = PlatformInfo(
            os_type="windows",
            os_release="10",
            arch="x86_64",
            is_wsl=False,
            shell_path="cmd.exe",
            shell_args=(),
            shell_type="cmd",
            env_set_template="set {key}={value}",
            path_separator=";",
            exit_code_var="%errorlevel%",
            process_group_creation_flag=0x00000200,
            safe_env_vars=frozenset(),
        )
        flavor = _get_flavor(pi)
        assert isinstance(flavor, WindowsFlavor)

        init_cmds = flavor.build_init_commands("/tmp", 10, 2048)
        assert "cd /d" in init_cmds[2]

        env_cmd = flavor.format_env_set("VAR", "VAL%UE")
        assert "set VAR=VAL%%UE" in env_cmd

        wrap_cmd = flavor.build_wrapped_command("echo hello", "EXIT:", "END", "%errorlevel%")
        assert "echo hello\\r\\n" in wrap_cmd or "echo hello\r\n" in wrap_cmd
        assert "EXIT:%errorlevel%" in wrap_cmd
        assert "END" in wrap_cmd

    @pytest.mark.asyncio
    async def test_check_health(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.state.name == "ACTIVE"
            assert session.is_alive is True
            assert session.sandbox_status is not None
            assert isinstance(session.is_sandboxed, bool)

            is_healthy = await session.check_health()
            assert is_healthy is True

            # Kill process and check health again
            assert session.process is not None
            session.process.kill()
            await session.process.wait()

            is_healthy_dead = await session.check_health()
            assert is_healthy_dead is False
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_a_shell_killed_during_a_command_reports_the_crash(self) -> None:
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            running = asyncio.create_task(session._execute_core("sleep 10", timeout=10))
            await asyncio.sleep(0.5)
            # SIGKILL (untrappable) mimics a real unexpected crash — the EXIT
            # trap cannot fire, stdout hits EOF and the session must surface
            # the fatal error instead of hanging.
            assert session.process is not None
            os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
            result = await running

            assert not result.success
            assert result.error is not None
            assert "Session process ended unexpectedly" in result.error
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_a_shell_terminated_during_a_command_fails_without_being_reported_as_a_crash(self) -> None:
        """SIGTERM is catchable: the EXIT trap emits the marker pair with the signal's status, so the
        command fails as terminated instead of being misreported as an unexpected crash or a success."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            running = asyncio.create_task(session._execute_core("sleep 10", timeout=10))
            await asyncio.sleep(0.5)
            assert session.process is not None
            os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
            result = await running

            assert result.error is None
            assert not result.success
            assert result.exit_code == 143
        finally:
            await session.close()
