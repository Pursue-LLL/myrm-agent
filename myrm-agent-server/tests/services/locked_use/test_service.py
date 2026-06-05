"""Tests for LockedUseService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.locked_use.service import LockedUseConfig, MacScreenUnlocker, locked_use_session


@pytest.fixture
def mock_sleep_inhibitor():
    with patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold") as mock_hold:
        mock_hold.return_value.__aenter__ = AsyncMock()
        mock_hold.return_value.__aexit__ = AsyncMock()
        yield mock_hold


class TestMacScreenUnlocker:
    @patch("subprocess.run")
    def test_is_locked_true(self, mock_run):
        mock_run.return_value = MagicMock(stdout="locked\n", returncode=0)
        assert MacScreenUnlocker.is_locked() is True

    @patch("subprocess.run")
    def test_is_locked_false(self, mock_run):
        mock_run.return_value = MagicMock(stdout="unlocked\n", returncode=0)
        assert MacScreenUnlocker.is_locked() is False

    @patch("subprocess.run")
    def test_is_locked_error(self, mock_run):
        mock_run.side_effect = Exception("error")
        assert MacScreenUnlocker.is_locked() is False

    @patch("subprocess.run")
    def test_get_password_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="my_password\n", returncode=0)
        assert MacScreenUnlocker.get_password() == "my_password"

    @patch("subprocess.run")
    def test_get_password_error(self, mock_run):
        mock_run.side_effect = Exception("error")
        assert MacScreenUnlocker.get_password() is None

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)  # Unlocked after attempt
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_success(self, mock_run, mock_popen, mock_is_locked, mock_get_password):
        assert await MacScreenUnlocker.unlock() is True
        assert mock_popen.called
        assert mock_run.called

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value=None)
    async def test_unlock_no_password(self, mock_get_password):
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)  # Still locked after attempt
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_failure(self, mock_run, mock_popen, mock_is_locked, mock_get_password):
        assert await MacScreenUnlocker.unlock() is False

    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "get_password", return_value="my_password")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)  # Unlocked after attempt
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    async def test_unlock_exception(self, mock_run, mock_popen, mock_is_locked, mock_get_password):
        mock_run.side_effect = Exception("error")
        assert await MacScreenUnlocker.unlock() is False

    @patch("subprocess.run")
    def test_relock(self, mock_run):
        MacScreenUnlocker.relock()
        assert mock_run.called


class TestLockedUseSession:
    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, return_value=True)
    @patch.object(MacScreenUnlocker, "relock")
    async def test_mac_locked_enabled(self, mock_relock, mock_unlock, mock_is_locked, mock_system, mock_sleep_inhibitor):
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_called_once()
        mock_unlock.assert_called_once()
        mock_relock.assert_called_once()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "relock")
    async def test_mac_unlocked_enabled(self, mock_relock, mock_unlock, mock_is_locked, mock_system, mock_sleep_inhibitor):
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_called_once()
        mock_unlock.assert_not_called()
        mock_relock.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked")
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "relock")
    async def test_mac_disabled(self, mock_relock, mock_unlock, mock_is_locked, mock_system, mock_sleep_inhibitor):
        config = LockedUseConfig(enabled=False)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_not_called()
        mock_unlock.assert_not_called()
        mock_relock.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Windows")
    @patch.object(MacScreenUnlocker, "is_locked")
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "relock")
    async def test_non_mac_enabled(self, mock_relock, mock_unlock, mock_is_locked, mock_system, mock_sleep_inhibitor):
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_not_called()
        mock_unlock.assert_not_called()
        mock_relock.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, return_value=False)
    @patch.object(MacScreenUnlocker, "relock")
    async def test_mac_locked_enabled_unlock_fails(
        self, mock_relock, mock_unlock, mock_is_locked, mock_system, mock_sleep_inhibitor
    ):
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_called_once()
        mock_unlock.assert_called_once()
        mock_relock.assert_not_called()  # Should not relock if we didn't unlock it
