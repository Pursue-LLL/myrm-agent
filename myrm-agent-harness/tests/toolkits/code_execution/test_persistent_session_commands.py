"""Tests for how a PersistentSession runs commands: marker safety, exit handling, syntax rejection, fidelity."""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from tests.toolkits.code_execution._session_helpers import make_config


class TestLifecycleSafety:
    """Lifecycle-safety guards for the persistent-session bug class: marker
    collision, ``exit`` killing the shell, and syntax errors killing the shell.
    Enforced via random markers + ``exit`` interceptor + ``bash -n`` gate.
    """

    @pytest.mark.asyncio
    async def test_marker_text_in_output_does_not_collide(self) -> None:
        """User output containing the legacy marker literals is not truncated."""
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
    async def test_stream_path_marker_like_output_not_truncated(self) -> None:
        """Stream path keeps marker-like user output intact (mirror of execute)."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            chunks = []
            async for chunk in session.execute_stream(
                'echo "__MYRM_END_00000000__"; echo "__MYRM_EXIT_ffffffff__"; echo done'
            ):
                chunks.append(chunk)
            combined = "".join(chunks)
            assert "__MYRM_END_00000000__" in combined
            assert "__MYRM_EXIT_ffffffff__" in combined
            assert "done" in combined
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
    async def test_exit_keeps_session_alive_and_cwd(self) -> None:
        """Trailing ``exit 0`` must not kill the persistent shell nor reset cwd."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("cd /tmp; pwd; exit 0")
            assert result.success
            assert session.is_alive
            cwd = await session.execute("pwd")
            assert "/tmp" in cwd.stdout
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
    async def test_exit_keeps_env(self) -> None:
        """Exported variables survive a command that ends with ``exit``."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            await session.execute("export MYRM_LC=42; exit 0")
            result = await session.execute('echo "v=$MYRM_LC"')
            assert "v=42" in result.stdout
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
    async def test_stream_path_rejects_syntax_error(self) -> None:
        """execute_stream applies the same syntax gate as execute."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            chunks = [c async for c in session.execute_stream("echo hi\n}\necho bye")]
            combined = "".join(chunks)
            assert "[ERROR]" in combined
            assert "syntax error" in combined
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_stream_path_comment_only_returns(self) -> None:
        """execute_stream also survives comment-only commands (shared wrapper)."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            chunks = []
            async with asyncio.timeout(6):
                async for c in session.execute_stream("# just a comment"):
                    chunks.append(c)
            combined = "".join(chunks)
            assert "[ERROR]" not in combined
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_stream_path_empty_command_returns(self) -> None:
        """execute_stream also survives blank commands (shared wrapper)."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            chunks = []
            async with asyncio.timeout(6):
                async for c in session.execute_stream("   "):
                    chunks.append(c)
            combined = "".join(chunks)
            assert "[ERROR]" not in combined
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
        """exit() interceptor works from inside a compound command."""
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
        """A trailing backslash continuation must not hang the shell and must leave the session usable.

        The continuation swallows the exit-code line of the wrapper, so the output boundary is corrupted
        and the shell is terminated on purpose; the contract is that the next command still runs.
        ``is_alive`` is not asserted because it flips only once the killed process has been reaped.
        """
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            _ = await asyncio.wait_for(session.execute("echo a \\", timeout=5), timeout=6)
            follow_up = await asyncio.wait_for(session.execute("echo still_usable", timeout=5), timeout=6)
            assert follow_up.success
            assert "still_usable" in follow_up.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_set_e_crash_emits_markers_not_sentinel(self) -> None:
        """Errexit crash (``set -e`` failing) terminates the non-interactive
        shell, but the injected EXIT trap still emits the marker pair with the
        real rc — the result reports the failure instead of misreporting an
        unexpected crash (which would trigger a pointless recovery)."""
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
    async def test_stream_path_scrubs_sensitive_info(self) -> None:
        """execute_stream PII-scrubs the real-time SSE output like the execute
        path: host paths and credential tokens must not reach the UI."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            chunks = []
            async for chunk in session.execute_stream(
                "echo /Users/alice/secret sk-ant-abcdefghijklmnopqrstuvwxyz123456"
            ):
                chunks.append(chunk)
            combined = "".join(chunks)
            assert "/Users/alice" not in combined
            assert "sk-ant-abcdefghijklmnopqrstuvwxyz123456" not in combined
            assert "<HOME>" in combined
        finally:
            await session.close()
