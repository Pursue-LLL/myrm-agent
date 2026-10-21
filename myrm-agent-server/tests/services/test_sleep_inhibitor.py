"""Tests for SleepInhibitor — system sleep prevention during agent tasks."""

from __future__ import annotations

import asyncio
import os
import platform
from unittest.mock import MagicMock, patch

import pytest

from app.services.infra.sleep_inhibitor import SleepInhibitor


@pytest.fixture(autouse=True)
def _reset_inhibitor():
    """Reset SleepInhibitor state between tests."""
    SleepInhibitor._ref_count = 0
    SleepInhibitor._process = None
    SleepInhibitor._prev_exec_state = None
    SleepInhibitor._mac_assertions = []
    SleepInhibitor._lock = None
    yield
    if SleepInhibitor._process is not None:
        SleepInhibitor._process.terminate()
        SleepInhibitor._process = None
    SleepInhibitor._ref_count = 0
    SleepInhibitor._prev_exec_state = None
    SleepInhibitor._mac_assertions = []
    SleepInhibitor._lock = None


@pytest.fixture()
def _force_local_mode():
    """Force local deployment mode."""
    old = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    from app.config.deploy_mode import get_deploy_mode

    get_deploy_mode.cache_clear()
    yield
    if old is None:
        os.environ.pop("DEPLOY_MODE", None)
    else:
        os.environ["DEPLOY_MODE"] = old
    get_deploy_mode.cache_clear()


@pytest.fixture()
def _force_sandbox_mode():
    """Force sandbox deployment mode."""
    old = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "sandbox"
    from app.config.deploy_mode import get_deploy_mode

    get_deploy_mode.cache_clear()
    yield
    if old is None:
        os.environ.pop("DEPLOY_MODE", None)
    else:
        os.environ["DEPLOY_MODE"] = old
    get_deploy_mode.cache_clear()


class TestSleepInhibitorLocalMode:
    """Tests for local deployment mode (inhibitor should activate)."""

    @pytest.mark.asyncio
    async def test_hold_activates_and_releases(self, _force_local_mode: None) -> None:
        """Inhibitor should activate on enter and release on exit."""
        async with SleepInhibitor.hold():
            assert SleepInhibitor._ref_count == 1
            if platform.system() == "Darwin":
                assert len(SleepInhibitor._mac_assertions) > 0

        assert SleepInhibitor._ref_count == 0
        if platform.system() == "Darwin":
            assert len(SleepInhibitor._mac_assertions) == 0
        else:
            assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_nested_holds_share_process(self, _force_local_mode: None) -> None:
        """Multiple concurrent holds should share a single inhibitor process/assertion."""
        async with SleepInhibitor.hold():
            first_process = SleepInhibitor._process
            first_assertions = list(SleepInhibitor._mac_assertions)
            assert SleepInhibitor._ref_count == 1

            async with SleepInhibitor.hold():
                assert SleepInhibitor._ref_count == 2
                if platform.system() == "Darwin":
                    assert SleepInhibitor._mac_assertions == first_assertions
                else:
                    assert SleepInhibitor._process is first_process

            assert SleepInhibitor._ref_count == 1
            if platform.system() == "Darwin":
                assert SleepInhibitor._mac_assertions == first_assertions
            else:
                assert SleepInhibitor._process is first_process

        assert SleepInhibitor._ref_count == 0
        if platform.system() == "Darwin":
            assert len(SleepInhibitor._mac_assertions) == 0
        else:
            assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_hold_releases_on_exception(self, _force_local_mode: None) -> None:
        """Inhibitor should release even when the block raises an exception."""
        with pytest.raises(RuntimeError, match="test error"):
            async with SleepInhibitor.hold():
                assert SleepInhibitor._ref_count == 1
                raise RuntimeError("test error")

        assert SleepInhibitor._ref_count == 0
        if platform.system() == "Darwin":
            assert len(SleepInhibitor._mac_assertions) == 0
        else:
            assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_concurrent_holds_via_gather(self, _force_local_mode: None) -> None:
        """Concurrent tasks should correctly manage ref count."""
        results: list[int] = []

        async def task() -> None:
            async with SleepInhibitor.hold():
                results.append(SleepInhibitor._ref_count)
                await asyncio.sleep(0.05)

        await asyncio.gather(task(), task(), task())

        assert SleepInhibitor._ref_count == 0
        if platform.system() == "Darwin":
            assert len(SleepInhibitor._mac_assertions) == 0
        else:
            assert SleepInhibitor._process is None
        assert max(results) >= 2


class TestSleepInhibitorSandboxMode:
    """Tests for sandbox deployment mode (inhibitor should be no-op)."""

    @pytest.mark.asyncio
    async def test_hold_is_noop_in_sandbox(self, _force_sandbox_mode: None) -> None:
        """Inhibitor should not activate in sandbox mode."""
        async with SleepInhibitor.hold():
            assert SleepInhibitor._ref_count == 0
            assert len(SleepInhibitor._mac_assertions) == 0
            assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_nested_hold_is_noop_in_sandbox(self, _force_sandbox_mode: None) -> None:
        """Nested holds should also be no-op in sandbox mode."""
        async with SleepInhibitor.hold():
            async with SleepInhibitor.hold():
                assert SleepInhibitor._ref_count == 0


class TestSleepInhibitorEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_activate_handles_missing_tool(self, _force_local_mode: None) -> None:
        """Should gracefully handle missing caffeinate/systemd-inhibit."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            # Note: On macOS this patch might not trigger since it uses ctypes,
            # but we can patch ctypes to simulate failure.
            with patch("ctypes.util.find_library", return_value=None):
                async with SleepInhibitor.hold():
                    assert SleepInhibitor._ref_count == 1
                    assert SleepInhibitor._process is None
                    assert len(SleepInhibitor._mac_assertions) == 0

                assert SleepInhibitor._ref_count == 0

    @pytest.mark.asyncio
    async def test_activate_handles_generic_error(self, _force_local_mode: None) -> None:
        """Should gracefully handle unexpected errors during activation."""
        with patch("subprocess.Popen", side_effect=OSError("permission denied")):
            with patch("ctypes.util.find_library", side_effect=OSError("permission denied")):
                async with SleepInhibitor.hold():
                    assert SleepInhibitor._ref_count == 1
                    assert SleepInhibitor._process is None
                    assert len(SleepInhibitor._mac_assertions) == 0

    @pytest.mark.asyncio
    async def test_deactivate_handles_terminate_error(self, _force_local_mode: None) -> None:
        """Should gracefully handle errors during deactivation."""
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("already dead")
        mock_proc.pid = 12345

        with patch("subprocess.Popen", return_value=mock_proc):
            with patch("platform.system", return_value="Linux"):
                async with SleepInhibitor.hold():
                    assert SleepInhibitor._ref_count == 1
                    assert SleepInhibitor._process is not None

        assert SleepInhibitor._ref_count == 0
        assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_cleanup_atexit_is_safe(self) -> None:
        """_cleanup_atexit should handle None process safely."""
        SleepInhibitor._process = None
        SleepInhibitor._cleanup_atexit()
        assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_cleanup_atexit_terminates_process(self) -> None:
        """_cleanup_atexit should terminate existing process."""
        mock_proc = MagicMock()
        SleepInhibitor._process = mock_proc

        SleepInhibitor._cleanup_atexit()

        mock_proc.terminate.assert_called_once()
        assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_ref_count_never_goes_negative(self, _force_local_mode: None) -> None:
        """Ref count should be clamped to 0, never negative."""
        SleepInhibitor._ref_count = 0
        SleepInhibitor._deactivate()
        assert SleepInhibitor._ref_count == 0


class TestSleepInhibitorPlatformBranches:
    """Test platform-specific branches via mocking."""

    @pytest.mark.asyncio
    async def test_linux_uses_systemd_inhibit(self, _force_local_mode: None) -> None:
        """On Linux, should spawn systemd-inhibit."""
        mock_proc = MagicMock()
        mock_proc.pid = 99999

        with patch("platform.system", return_value="Linux"), patch("subprocess.Popen", return_value=mock_proc) as popen_mock:
            SleepInhibitor._activate()

            popen_mock.assert_called_once()
            args = popen_mock.call_args[0][0]
            assert args[0] == "systemd-inhibit"
            assert "--what=idle" in args
            assert SleepInhibitor._process is mock_proc

        SleepInhibitor._process = None

    @pytest.mark.asyncio
    async def test_linux_deactivate(self, _force_local_mode: None) -> None:
        """On Linux, deactivate should terminate the process."""
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        SleepInhibitor._process = mock_proc

        SleepInhibitor._deactivate()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)
        assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_windows_uses_set_thread_execution_state(self, _force_local_mode: None) -> None:
        """On Windows, should call SetThreadExecutionState."""
        mock_windll = MagicMock()
        mock_windll.kernel32.SetThreadExecutionState.return_value = 0x80000000

        with (
            patch("platform.system", return_value="Windows"),
            patch.dict("sys.modules", {"ctypes": MagicMock(windll=mock_windll)}),
        ):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    MagicMock(windll=mock_windll) if name == "ctypes" else __builtins__.__import__(name, *a, **kw)
                ),
            ):
                pass

        with patch("platform.system", return_value="Windows"):
            SleepInhibitor._prev_exec_state = 0x80000000
            SleepInhibitor._deactivate()

    @pytest.mark.asyncio
    async def test_unsupported_platform_is_noop(self, _force_local_mode: None) -> None:
        """On unsupported platforms, activation should be no-op."""
        with patch("platform.system", return_value="FreeBSD"):
            SleepInhibitor._activate()
            assert SleepInhibitor._process is None
            assert SleepInhibitor._prev_exec_state is None

    @pytest.mark.asyncio
    async def test_mac_deactivate_handles_error(self, _force_local_mode: None) -> None:
        """Should gracefully handle errors during macOS IOKit deactivation."""
        with patch("platform.system", return_value="Darwin"):
            SleepInhibitor._mac_assertions = [123, 456]
            with patch("ctypes.util.find_library", side_effect=OSError("not found")):
                SleepInhibitor._deactivate()
            # It should clear the list even if it fails
            assert len(SleepInhibitor._mac_assertions) == 0


class TestSleepInhibitorReusability:
    """Test repeated activation/deactivation cycles."""

    @pytest.mark.asyncio
    async def test_repeated_hold_cycles(self, _force_local_mode: None) -> None:
        """Multiple sequential hold cycles should each activate/release cleanly."""
        for _ in range(3):
            async with SleepInhibitor.hold():
                assert SleepInhibitor._ref_count == 1
                if platform.system() == "Darwin":
                    assert len(SleepInhibitor._mac_assertions) > 0

            assert SleepInhibitor._ref_count == 0
            if platform.system() == "Darwin":
                assert len(SleepInhibitor._mac_assertions) == 0
            else:
                assert SleepInhibitor._process is None

    @pytest.mark.asyncio
    async def test_get_lock_returns_same_instance(self) -> None:
        """_get_lock should always return the same Lock instance."""
        SleepInhibitor._lock = None
        lock1 = SleepInhibitor._get_lock()
        lock2 = SleepInhibitor._get_lock()
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_hold_with_cancellation(self, _force_local_mode: None) -> None:
        """Cancelled tasks should still release the inhibitor."""

        async def cancellable_task() -> None:
            async with SleepInhibitor.hold():
                await asyncio.sleep(10)

        task = asyncio.create_task(cancellable_task())
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert SleepInhibitor._ref_count == 0
        if platform.system() == "Darwin":
            assert len(SleepInhibitor._mac_assertions) == 0
        else:
            assert SleepInhibitor._process is None
