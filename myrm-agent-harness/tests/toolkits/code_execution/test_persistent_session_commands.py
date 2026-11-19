"""Tests for how a PersistentSession runs commands: marker safety, exit handling, syntax rejection, fidelity."""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from tests.toolkits.code_execution._session_helpers import captured_stdout_chunks, make_config


class TestLifecycleSafety:
    """Lifecycle-safety guards for the persistent-session bug class: marker
    collision, ``exit`` killing the shell, and syntax errors killing the shell.
    Enforced via random markers + a script per command + ``bash -n`` gate.
    """

    @pytest.mark.asyncio
    async def test_marker_text_in_output_does_not_collide(self) -> None:
        """User output containing a fixed marker literal such as ``__MYRM_EXIT__`` is not truncated."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute('echo "hello __MYRM_EXIT__ world"; echo after')
            assert result.success
            assert result.exit_code == 0
            assert "hello __MYRM_EXIT__ world" in result.stdout
            assert "after" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_marker_sequence_in_output_not_truncated(self) -> None:
        """A multi-line payload containing both marker literals passes through."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("printf 'a\\n__MYRM_EXIT__\\nb\\n__MYRM_END__\\nc\\n'")
            assert result.success
            assert result.exit_code == 0
            assert "a" in result.stdout and "b" in result.stdout and "c" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_markers_are_random_per_command(self) -> None:
        """Each execution gets unique boundary markers."""
        from myrm_agent_harness.toolkits.code_execution.session.command_stream import (
            _generate_marker,
        )

        a_end, b_end = _generate_marker("END"), _generate_marker("END")
        a_exit, b_exit = _generate_marker("EXIT"), _generate_marker("EXIT")
        assert a_end != b_end
        assert a_exit != b_exit
        assert a_end.startswith("__MYRM_END_")
        assert a_exit.startswith("__MYRM_EXIT_")

    @pytest.mark.asyncio
    async def test_exit_keeps_session_alive(self) -> None:
        """Trailing ``exit 0`` must not kill the persistent shell."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("cd /tmp; pwd; exit 0")
            assert result.success
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_exit_nonzero_propagates(self) -> None:
        """``exit 5`` surfaces rc=5 while the session survives."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("exit 5")
            assert not result.success
            assert result.exit_code == 5
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_nested_bash_exit_unaffected(self) -> None:
        """A nested ``bash -c`` process still honors real ``exit`` semantics."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute('bash -c "exit 3"; echo rc=$?')
            assert result.success
            assert "rc=3" in result.stdout
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_bare_brace_rejected_without_killing_session(self) -> None:
        """A bare ``}`` line is a syntax error caught by the pre-check gate."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("echo hi\n}\necho bye")
            assert not result.success
            assert "syntax error" in (result.error or "")
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_unclosed_if_rejected_without_killing_session(self) -> None:
        """An unterminated ``if`` block is caught before reaching the shell."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("if true; then\n echo x")
            assert not result.success
            assert "unexpected end of file" in (result.error or "")
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_multiline_for_loop_fidelity(self) -> None:
        """Multi-line compound commands still execute faithfully."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute('for i in 1 2; do\n  echo "x$i"\ndone')
            assert result.success
            assert "x1" in result.stdout and "x2" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_heredoc_fidelity(self) -> None:
        """Heredoc bodies pass the pre-check and run correctly."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute(
                "cat <<'EOF' > /tmp/myrm_lc_heredoc.txt\nhello\n}\nEOF\ncat /tmp/myrm_lc_heredoc.txt"
            )
            assert result.success
            assert "hello" in result.stdout and "}" in result.stdout
        finally:
            await session.execute("rm -f /tmp/myrm_lc_heredoc.txt")
            await session.close()

    @pytest.mark.asyncio
    async def test_background_child_does_not_delay_main(self) -> None:
        """A background child holding the stdout pipe must not block execution."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await asyncio.wait_for(session.execute("sleep 5 & echo done", timeout=5), timeout=6)
            assert result.success
            assert "done" in result.stdout
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_nohup_background_returns_immediately(self) -> None:
        """Detached background processes do not delay the current command."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await asyncio.wait_for(
                session.execute("nohup sleep 3 >/dev/null 2>&1 & echo started", timeout=5),
                timeout=6,
            )
            assert result.success
            assert "started" in result.stdout
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_comment_only_command_returns_immediately(self) -> None:
        """A lone comment line must not wedge the wrapper into an open block."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await asyncio.wait_for(session.execute("# just a comment", timeout=5), timeout=6)
            assert result.success
            assert result.exit_code == 0
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_empty_command_no_crash(self) -> None:
        """Blank commands are no-ops that succeed without killing the shell."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await asyncio.wait_for(session.execute("   ", timeout=5), timeout=6)
            assert result.success
            assert result.exit_code == 0
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_comment_then_command(self) -> None:
        """A leading comment line does not interfere with the real command."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("# header\necho real")
            assert result.success
            assert "real" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_exit_inside_loop(self) -> None:
        """An ``exit`` inside a compound command ends the command with that status."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("for i in 1 2; do exit 7; done")
            assert not result.success
            assert result.exit_code == 7
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_trailing_backslash_no_hang(self) -> None:
        """A trailing backslash continuation ends with its script: it cannot swallow the exit-code line of the wrapper
        around the command, which would corrupt the output boundary and cost the shell."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await asyncio.wait_for(session.execute("echo a \\", timeout=5), timeout=6)
            assert result.success
            assert result.stdout == "a"

            follow_up = await asyncio.wait_for(session.execute("echo still_usable", timeout=5), timeout=6)
            assert follow_up.success
            assert "still_usable" in follow_up.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_set_e_crash_reports_the_exit_code_not_a_dead_shell(self) -> None:
        """A ``set -e`` failure ends the command with the failing status: the
        result reports the failure instead of an unexpected shell death."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("set -e; false; echo NEVER")
            assert not result.success
            assert result.exit_code == 1
            assert result.error is None or "Session process ended unexpectedly" not in result.error
            assert "NEVER" not in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_live_output_scrubs_sensitive_info(self) -> None:
        """The real-time SSE output is PII-scrubbed: host paths and credential
        tokens must not reach the UI."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            with captured_stdout_chunks() as chunks:
                result = await session.execute("echo /Users/alice/secret sk-ant-abcdefghijklmnopqrstuvwxyz123456")
            assert result.success
            shown = "".join(chunks)
            assert "/Users/alice" not in shown
            assert "sk-ant-abcdefghijklmnopqrstuvwxyz123456" not in shown
            assert "<HOME>" in shown
        finally:
            await session.close()
