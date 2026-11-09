# Before importing, we must mock sys.platform to properly test branches.
# However, os_compat uses IS_WIN at module level.
# We will reload the module with patching.
import importlib
import signal
from collections.abc import Iterator
from unittest.mock import patch

import pytest

import myrm_agent_harness.utils.os_compat as os_compat


@pytest.fixture
def win32_env() -> Iterator[None]:
    with patch("sys.platform", "win32"):
        importlib.reload(os_compat)
        yield
    importlib.reload(os_compat)


@pytest.fixture
def posix_env() -> Iterator[None]:
    with patch("sys.platform", "linux"):
        importlib.reload(os_compat)
        yield
    importlib.reload(os_compat)


def test_get_process_group_kwargs_win32(win32_env: None) -> None:
    kwargs = os_compat.get_process_group_kwargs()
    assert "creationflags" in kwargs


def test_get_process_group_kwargs_posix(posix_env: None) -> None:
    kwargs = os_compat.get_process_group_kwargs()
    assert "start_new_session" in kwargs
    assert kwargs["start_new_session"] is True


def test_kill_process_group_win32(win32_env: None) -> None:
    with patch("subprocess.run") as mock_run:
        os_compat.kill_process_group(12345)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "taskkill" in args
        assert str(12345) in args


def test_kill_process_group_posix(posix_env: None) -> None:
    def mock_getpgid(p: int) -> int:
        if p == 12345:
            return 54321
        return 11111

    with (
        patch("os.getpgid", side_effect=mock_getpgid),
        patch("os.getpid", return_value=11111),
        patch("os.killpg") as mock_killpg,
    ):
        os_compat.kill_process_group(12345)
        mock_killpg.assert_called_once_with(54321, signal.SIGKILL)

    # Test safety check (shares process group with parent)
    def mock_getpgid_same(p: int) -> int:
        return 11111

    with (
        patch("os.getpgid", side_effect=mock_getpgid_same),
        patch("os.getpid", return_value=11111),
        patch("os.kill") as mock_kill,
    ):
        os_compat.kill_process_group(12345)
        mock_kill.assert_called_once_with(12345, signal.SIGKILL)

    # Test process lookup error
    with patch("os.getpgid", side_effect=ProcessLookupError):
        # Should silently ignore
        os_compat.kill_process_group(12345)


def test_kill_spawned_group_signals_the_group_named_after_the_child_pid(posix_env: None) -> None:
    with patch("os.killpg") as mock_killpg:
        os_compat.kill_spawned_group(12345)
        mock_killpg.assert_called_once_with(12345, signal.SIGKILL)


@pytest.mark.parametrize("error", [ProcessLookupError, PermissionError])
def test_kill_spawned_group_ignores_a_group_that_is_gone_or_not_ours(posix_env: None, error: type[Exception]) -> None:
    with patch("os.killpg", side_effect=error):
        os_compat.kill_spawned_group(12345)


@pytest.mark.parametrize("pid", [0, 1, -5])
def test_kill_spawned_group_never_signals_our_own_group_or_init(posix_env: None, pid: int) -> None:
    with patch("os.killpg") as mock_killpg:
        os_compat.kill_spawned_group(pid)
        mock_killpg.assert_not_called()


def test_kill_spawned_group_win32_kills_the_tree_from_the_pid(win32_env: None) -> None:
    with patch("subprocess.run") as mock_run:
        os_compat.kill_spawned_group(12345)
        assert "taskkill" in mock_run.call_args[0][0]
        assert "12345" in mock_run.call_args[0][0]


def test_sigkill_is_the_posix_force_kill_signal(posix_env: None) -> None:
    assert os_compat.SIGKILL is signal.SIGKILL
    assert os_compat.kill_process_group.__defaults__ == (signal.SIGKILL,)


def test_sigkill_falls_back_to_sigterm_where_windows_has_no_sigkill(
    win32_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`signal.SIGKILL` as a default argument made the whole module unimportable on Windows."""
    monkeypatch.delattr(signal, "SIGKILL", raising=False)

    importlib.reload(os_compat)

    assert os_compat.SIGKILL is signal.SIGTERM
    assert os_compat.kill_process_group.__defaults__ == (signal.SIGTERM,)


def test_terminate_process_graceful_escalates_to_sigkill(posix_env: None) -> None:
    alive = {"value": True}

    def mock_getpgid(pid: int) -> int:
        if pid == 12345:
            return 54321
        return 11111

    def mock_killpg(_pgid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            alive["value"] = False

    def mock_kill(pid: int, sig: int) -> None:
        if pid == 12345 and sig == 0 and not alive["value"]:
            raise ProcessLookupError

    with (
        patch("os.getpgid", side_effect=mock_getpgid),
        patch("os.getpid", return_value=11111),
        patch("os.killpg", side_effect=mock_killpg),
        patch("os.kill", side_effect=mock_kill),
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0.0, 3.0]),
    ):
        os_compat.terminate_process_graceful(12345, grace_seconds=2.0)

    assert alive["value"] is False
