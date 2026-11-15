"""Tests for PersistentSession state transitions, recovery paths, output limits, tee logs and disk quota."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from myrm_agent_harness.toolkits.code_execution.session.models import SessionState
from tests.toolkits.code_execution._session_helpers import make_config, state_of


class TestStreamThrottlingAndOOM:
    @pytest.mark.asyncio
    async def test_sse_throttle_and_valve(self) -> None:
        """Test SSE throttle (10FPS) and volume valve (500KB) during execute_stream."""
        session = LocalPersistentSession(make_config(timeout=10))
        await session.start()
        try:
            # Output 600KB of data to trigger the 500KB valve
            cmd = "python3 -c \"print('x' * 600000)\""

            chunks = []
            async for chunk in session.execute_stream(cmd):
                chunks.append(chunk)

            warning_found = False
            for c in chunks:
                if "System Warning: Terminal stream suspended" in c:
                    warning_found = True
                    break

            assert warning_found, "Volume valve did not trigger"
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_oom_truncation(self) -> None:
        """Output beyond MAX_OUTPUT_CHARS is cut once, in the session: the result fits the cap with both notes in it.

        ExecutionResult cuts stdout again at the cap, and that cut would take the middle out of the result,
        the notice and its count of the dropped characters with it.
        """
        session = LocalPersistentSession(make_config(timeout=15))
        await session.start()
        try:
            from myrm_agent_harness.toolkits.code_execution.executors.common.executor_utils import (
                MAX_OUTPUT_CHARS,
            )
            from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult

            # 10,000 lines of 21 characters: 210,000 characters, beyond MAX_OUTPUT_CHARS.
            written = 10_000 * 21
            result = await session.execute("python3 -c \"for i in range(10000): print('A' * 20)\"")

            assert result.success
            assert len(result.stdout) <= MAX_OUTPUT_CHARS
            notice = re.search(
                r"\[System Warning: The middle (\d+) characters of output were truncated to prevent memory overflow\]",
                result.stdout,
            )
            assert notice is not None
            assert "[System Note: Output was truncated. The FULL original output was stream-saved to" in result.stdout
            # The count is what the result lost: the overflow, and the room the two notes take.
            assert written - MAX_OUTPUT_CHARS <= int(notice[1]) <= written - MAX_OUTPUT_CHARS + 1_000

            handed_on = ExecutionResult(success=True, stdout=result.stdout).stdout
            assert "[Truncated:" not in handed_on
            assert notice[0] in handed_on
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_output_between_the_head_and_the_cap_is_returned_whole(self) -> None:
        """Nothing is dropped below the cap: no notice splits the output where the head ends, no note follows it."""
        session = LocalPersistentSession(make_config(timeout=15))
        await session.start()
        try:
            result = await session.execute("python3 -c \"print('A' * 100000)\"")

            assert result.success
            assert result.stdout == "A" * 100_000
        finally:
            await session.close()


class TestStateMachine:
    @pytest.mark.asyncio
    async def test_transit_same_state_noop(self) -> None:
        """Transitioning to same state is a no-op."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.state == SessionState.ACTIVE
            await session._transit_state(SessionState.ACTIVE)
            assert session.state == SessionState.ACTIVE
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_start_when_already_alive(self) -> None:
        """Calling start() on an active session is a no-op."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.process is not None
            pid_before = session.process.pid
            await session.start()
            assert session.process.pid == pid_before
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_close_when_already_closing(self) -> None:
        """_close_unlocked returns immediately when already CLOSING."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            session._state = SessionState.CLOSING
            await session._close_unlocked()
            assert session._state == SessionState.CLOSING
        finally:
            if session.process and session.process.returncode is None:
                session.process.kill()
                await session.process.wait()

    @pytest.mark.asyncio
    async def test_execute_core_no_process(self) -> None:
        """_execute_core returns error when process is None."""
        session = LocalPersistentSession(make_config())
        session.process = None
        result = await session._execute_core("echo x", timeout=5)
        assert not result.success
        assert result.error == "Process unavailable"


class TestRecoveryPath:
    @pytest.mark.asyncio
    async def test_auto_recover_on_process_death(self) -> None:
        """Execute should auto-recover when process dies mid-flight."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute("echo alive")
            assert result.success

            assert session.process is not None
            session.process.kill()
            await session.process.wait()

            result = await session.execute("echo recovered")
            assert result.success
            assert "recovered" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_start_failure_transitions_to_terminated(self) -> None:
        """When _create_process fails, state transitions to TERMINATED."""
        from unittest.mock import AsyncMock, patch

        session = LocalPersistentSession(make_config())

        with patch.object(
            session,
            "_create_process",
            new_callable=AsyncMock,
            side_effect=OSError("spawn fail"),
        ):
            with pytest.raises(OSError, match="spawn fail"):
                await session.start()
            assert session.state == SessionState.TERMINATED

    @pytest.mark.asyncio
    async def test_recover_and_retry_failure(self) -> None:
        """_recover_and_retry returns error result when recovery itself fails."""
        from unittest.mock import AsyncMock, patch

        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            with patch.object(
                session,
                "_create_process",
                new_callable=AsyncMock,
                side_effect=OSError("fail"),
            ):
                result = await session._recover_and_retry("echo x", timeout=5)
                assert not result.success
                assert result.error is not None
                assert "Recovery failed" in result.error
                assert session.state == SessionState.TERMINATED
        finally:
            if session.process and session.process.returncode is None:
                session.process.kill()
                await session.process.wait()


class TestCheckHealthEdge:
    @pytest.mark.asyncio
    async def test_check_health_exception(self) -> None:
        """check_health returns False when execute raises."""
        from unittest.mock import AsyncMock, patch

        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            with patch.object(
                session,
                "execute",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ):
                result = await session.check_health()
                assert result is False
        finally:
            await session.close()


class TestInitializeShellEdge:
    @pytest.mark.asyncio
    async def test_initialize_shell_no_process(self) -> None:
        """_initialize_shell returns early when process is None."""
        session = LocalPersistentSession(make_config())
        session.process = None
        await session._initialize_shell()

    @pytest.mark.asyncio
    async def test_initialize_shell_with_env(self) -> None:
        """_initialize_shell injects env vars from config."""
        config = make_config()
        config.env = {"MY_VAR": "test_value"}
        session = LocalPersistentSession(config)
        await session.start()
        try:
            result = await session.execute("echo $MY_VAR")
            assert result.success
            assert "test_value" in result.stdout
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_initialize_shell_special_chars_env_preserved(self) -> None:
        """Env values with $, backticks, quotes and backslashes stay literal.

        ``format_env_set`` must not let the shell re-expand ``$VAR``/backticks
        embedded in a user-provided env value (e.g. API tokens).
        """
        config = make_config()
        config.env = {"MY_SPECIAL": "a\"b\\c d$HOME `whoami` 'q'"}
        session = LocalPersistentSession(config)
        await session.start()
        try:
            result = await session.execute("printf '%s' \"$MY_SPECIAL\"")
            assert result.success
            assert result.stdout == "a\"b\\c d$HOME `whoami` 'q'"
        finally:
            await session.close()


class TestEnsureActiveEdge:
    @pytest.mark.asyncio
    async def test_ensure_active_from_idle(self) -> None:
        """_ensure_active starts session when in IDLE state."""
        session = LocalPersistentSession(make_config())
        assert session.state == SessionState.IDLE
        await session._ensure_active()
        try:
            assert state_of(session) == SessionState.ACTIVE
            assert session.is_alive
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_ensure_active_from_terminated(self) -> None:
        """_ensure_active restarts session from TERMINATED state."""
        session = LocalPersistentSession(make_config())
        await session.start()
        await session.close()
        assert session.state == SessionState.TERMINATED
        await session._ensure_active()
        try:
            assert state_of(session) == SessionState.ACTIVE
        finally:
            await session.close()


class TestAutoTeeAndDiskQuota:
    @pytest.mark.asyncio
    async def test_auto_tee_generation_and_lru(self, tmp_path: Path) -> None:
        """Test that tee files are generated and LRU cleanup works."""
        import glob

        config = make_config(work_dir=str(tmp_path))
        session = LocalPersistentSession(config)
        await session.start()
        try:
            # Execute a simple command
            result = await session.execute("echo 'test_tee_output'")
            assert result.success

            # Check if tee file was created
            tee_dir = os.path.join(config.work_dir, ".myrm", "tee")
            assert os.path.exists(tee_dir)
            log_files = glob.glob(os.path.join(tee_dir, "cmd_*.log"))
            assert len(log_files) >= 1

            # Read the latest tee file
            latest_log = max(log_files, key=os.path.getmtime)
            with open(latest_log, encoding="utf-8") as f:
                content = f.read()
                assert "test_tee_output" in content
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_disk_quota_truncation(self, tmp_path: Path) -> None:
        """Test that the disk quota truncates the tee file and injects warnings."""
        import glob
        from unittest.mock import patch

        config = make_config(timeout=30, work_dir=str(tmp_path))
        session = LocalPersistentSession(config)

        test_limit = 1 * 1024 * 1024  # 1MB limit for fast testing

        await session.start()
        try:
            with patch(
                "myrm_agent_harness.toolkits.code_execution.session.stream_output_processor._TEE_MAX_BYTES",
                test_limit,
            ):
                cmd = "python3 -c \"print('B' * 2000000)\""

                chunks = []
                async for chunk in session.execute_stream(cmd):
                    chunks.append(chunk)

                output = "".join(chunks)
                assert "Terminal stream suspended to prevent UI freeze" in output

                tee_dir = os.path.join(config.work_dir, ".myrm", "tee")
                log_files = glob.glob(os.path.join(tee_dir, "cmd_*.log"))
                latest_log = max(log_files, key=os.path.getmtime)

                file_size = os.path.getsize(latest_log)
                assert file_size <= test_limit + 1024
                assert file_size >= test_limit * 0.8  # at least 80% written

                with open(latest_log, encoding="utf-8") as f:
                    content = f.read()
                    assert "[System Warning: Tee log file exceeded 50MB hard limit and was truncated.]" in content

        finally:
            await session.close()
