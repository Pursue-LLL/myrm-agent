"""Tests for PersistentSession process-group and process-tree termination."""

from __future__ import annotations

import asyncio
import contextlib
import os

import pytest

from myrm_agent_harness.toolkits.code_execution.session import (
    LocalPersistentSession,
)
from tests.toolkits.code_execution._session_helpers import make_config, pid_exists


class TestProcessGroupKill:
    @pytest.mark.asyncio
    async def test_start_new_session_set(self) -> None:
        """Verify bash process runs in its own session (process group)."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            assert session.process is not None
            pid = session.process.pid
            assert pid is not None
            pgid = os.getpgid(pid)
            assert pgid == pid
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_child_processes_killed(self) -> None:
        """Child processes spawned by bash should be killed on close."""
        session = LocalPersistentSession(make_config())
        await session.start()
        try:
            result = await session.execute(
                "python3 -c 'import time,os; print(os.getpid()); time.sleep(300)' &\nsleep 0.3 && jobs -p"
            )
            if not result.success:
                pytest.skip("fork not available in test environment")

            lines = result.stdout.strip().splitlines()
            pids = [int(p) for p in lines if p.strip().isdigit()]
            if not pids:
                pytest.skip("could not capture child PID")

            child_pid = pids[0]
            assert pid_exists(child_pid)
            await session.close()
            await asyncio.sleep(0.3)
            assert not pid_exists(child_pid)
        finally:
            if session.process:
                await session.close()

    @pytest.mark.asyncio
    async def test_cancel_during_close_still_kills_child(self) -> None:
        """Shield ensures _kill_process_group completes even under cancellation."""
        from unittest.mock import patch

        session = LocalPersistentSession(make_config())
        await session.start()

        kill_completed = False
        original_kill = session._kill_process_group

        async def slow_kill(grace_period: float = 2.0) -> None:
            nonlocal kill_completed
            await original_kill(grace_period)
            kill_completed = True

        try:
            result = await session.execute(
                "python3 -c 'import time,os; print(os.getpid()); time.sleep(300)' &\nsleep 0.3 && jobs -p"
            )
            if not result.success:
                pytest.skip("fork not available in test environment")
            lines = result.stdout.strip().splitlines()
            pids = [int(p) for p in lines if p.strip().isdigit()]
            if not pids:
                pytest.skip("could not capture child PID")

            child_pid = pids[0]
            assert pid_exists(child_pid)

            with patch.object(session, "_kill_process_group", side_effect=slow_kill):
                close_task = asyncio.create_task(session.close())
                await asyncio.sleep(0.05)
                close_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await close_task

            await asyncio.sleep(0.5)
            assert kill_completed, "shield must let _kill_process_group finish"
            assert not pid_exists(child_pid), "child process must be dead"
        finally:
            if session.process and session.process.returncode is None:
                session.process.kill()
                await session.process.wait()

    @pytest.mark.asyncio
    async def test_kill_process_group_already_dead(self) -> None:
        """_kill_process_group should not raise if process already exited."""
        session = LocalPersistentSession(make_config())
        await session.start()
        assert session.process is not None
        session.process.kill()
        await session.process.wait()
        await session._kill_process_group()

    @pytest.mark.asyncio
    async def test_kill_posix_shared_pgid_falls_back(self) -> None:
        """When child shares parent's pgid, kill_process_tree terminates only the child."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None  # still running: a reaped shell is never signalled
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=None)

        my_pgid = os.getpgid(os.getpid())
        with (
            patch("os.getpgid", return_value=my_pgid),
            patch("os.killpg") as mock_killpg,
            # The mock pid is made up: it must not be looked up in the real process table.
            patch(
                "myrm_agent_harness.toolkits.code_execution.session.process_tree._descendants",
                return_value=[],
            ),
        ):
            await kill_process_tree(mock_process, is_windows=False, grace_period=1.0)
            mock_process.terminate.assert_called_once()
            mock_killpg.assert_not_called()

    @pytest.mark.asyncio
    async def test_kill_posix_different_pgid_kills_group(self) -> None:
        """When child has its own pgid, killpg should be used."""
        import signal
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.returncode = None
        mock_process.wait = AsyncMock(return_value=None)

        real_my_pgid = os.getpgid(os.getpid())
        fake_child_pgid = 99999
        with (
            patch(
                "os.getpgid",
                side_effect=lambda pid: fake_child_pgid if pid == 99999 else real_my_pgid,
            ),
            patch("os.killpg") as mock_killpg,
            # The mock pid is made up: it must not be looked up in the real process table.
            patch(
                "myrm_agent_harness.toolkits.code_execution.session.process_tree._descendants",
                return_value=[],
            ),
        ):
            await kill_process_tree(mock_process, is_windows=False, grace_period=1.0)
            mock_killpg.assert_any_call(fake_child_pgid, signal.SIGTERM)


class TestKillProcessTreeEdgeCases:
    @pytest.mark.asyncio
    async def test_pid_is_none(self) -> None:
        """kill_process_tree should return immediately if pid is None."""
        from unittest.mock import MagicMock

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = None
        await kill_process_tree(mock_process, is_windows=False)

    @pytest.mark.asyncio
    async def test_windows_taskkill(self) -> None:
        """Windows path uses taskkill /F /T /PID."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_sub = MagicMock()
        mock_sub.wait = AsyncMock(return_value=0)

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_sub,
        ) as mock_exec:
            await kill_process_tree(mock_process, is_windows=True)
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "taskkill" in args
            assert "/F" in args
            assert "/T" in args

    @pytest.mark.asyncio
    async def test_windows_taskkill_failure_fallback(self) -> None:
        """Windows path falls back to process.kill() on taskkill failure."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None
        mock_process.kill = MagicMock()

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=OSError("fail"),
        ):
            await kill_process_tree(mock_process, is_windows=True)
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_shared_pgid_sigterm_timeout_kills(self) -> None:
        """When shared pgid and SIGTERM times out, falls back to process.kill()."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None  # still running: a reaped shell is never signalled
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(side_effect=TimeoutError)

        my_pgid = os.getpgid(os.getpid())
        with (
            patch("os.getpgid", return_value=my_pgid),
            patch(
                "myrm_agent_harness.toolkits.code_execution.session.process_tree._descendants",
                return_value=[],
            ),
        ):
            await kill_process_tree(mock_process, is_windows=False, grace_period=0.1)
            mock_process.terminate.assert_called_once()
            mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_pgid_sigterm_timeout_sigkill(self) -> None:
        """When different pgid and SIGTERM times out, falls back to SIGKILL on group."""
        import signal
        from unittest.mock import AsyncMock, MagicMock, patch

        from myrm_agent_harness.toolkits.code_execution.session.process_tree import (
            kill_process_tree,
        )

        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.returncode = None
        mock_process.wait = AsyncMock(side_effect=TimeoutError)

        real_my_pgid = os.getpgid(os.getpid())
        fake_child_pgid = 99999
        with (
            patch(
                "os.getpgid",
                side_effect=lambda pid: fake_child_pgid if pid == 99999 else real_my_pgid,
            ),
            patch("os.killpg") as mock_killpg,
            # The mock pid is made up: it must not be looked up in the real process table.
            patch(
                "myrm_agent_harness.toolkits.code_execution.session.process_tree._descendants",
                return_value=[],
            ),
        ):
            await kill_process_tree(mock_process, is_windows=False, grace_period=0.1)
            mock_killpg.assert_any_call(fake_child_pgid, signal.SIGTERM)
            mock_killpg.assert_any_call(fake_child_pgid, signal.SIGKILL)
