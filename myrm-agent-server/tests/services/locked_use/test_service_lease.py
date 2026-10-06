"""Tests for the re-lock chain and the Computer Use session lease.

[INPUT]
- app.services.locked_use.service（POS: relock_verified / ensure_locked / release_unlock_lease / locked_use_session）

[OUTPUT]
- 校验回锁（请求已发 ≠ 确已锁定）、租约交还门禁、会话上下文管理器的租约获取/交还断言

[POS]
与 test_service.py（探测 / 解锁原语）互补：本文件覆盖回锁校验与租约生命周期。
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.locked_use.service import (
    LockedUseConfig,
    MacScreenUnlocker,
    locked_use_session,
    release_unlock_lease,
)


@pytest.fixture
def mock_sleep_inhibitor() -> Iterator[MagicMock]:
    with patch("app.services.infra.sleep_inhibitor.SleepInhibitor.hold") as mock_hold:
        mock_hold.return_value.__aenter__ = AsyncMock()
        # 必须返回 False：默认的 MagicMock 返回值为真，会把会话体内的异常静默吞掉。
        mock_hold.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_hold


@pytest.fixture
def lease_bit() -> Iterator[tuple[MagicMock, MagicMock]]:
    """隔离租约位文件写入：返回 (mark, clear) 两个探针。"""
    with (
        patch("app.services.locked_use.service.mark_pending_auto_unlock") as mark,
        patch("app.services.locked_use.service.clear_pending_auto_unlock") as clear,
    ):
        yield mark, clear


class TestRelockVerified:
    """relock_verified 是「请求已发」与「确已锁定」之间的唯一校验关口。"""

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "relock", return_value=True)
    async def test_success_on_first_attempt(
        self, mock_relock: MagicMock, mock_is_locked: MagicMock, mock_sleep: AsyncMock
    ) -> None:
        assert await MacScreenUnlocker.relock_verified() is True
        mock_relock.assert_called_once()

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "is_locked", side_effect=[False, False, True])
    @patch.object(MacScreenUnlocker, "relock", return_value=True)
    async def test_retries_until_probe_confirms(
        self, mock_relock: MagicMock, mock_is_locked: MagicMock, mock_sleep: AsyncMock
    ) -> None:
        assert await MacScreenUnlocker.relock_verified() is True
        assert mock_relock.call_count == 3

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)
    @patch.object(MacScreenUnlocker, "relock", return_value=True)
    async def test_exhausted_attempts_report_failure(
        self, mock_relock: MagicMock, mock_is_locked: MagicMock, mock_sleep: AsyncMock
    ) -> None:
        """命令退出零但探测始终未锁定：必须返回 False（不得报喜）。"""
        assert await MacScreenUnlocker.relock_verified() is False
        assert mock_relock.call_count == 3

    @patch("subprocess.run")
    def test_relock_reports_command_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], returncode=1)
        assert MacScreenUnlocker.relock() is False


class TestEnsureLocked:
    @pytest.mark.asyncio
    @patch.object(MacScreenUnlocker, "relock_verified", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    async def test_already_locked_sends_no_lock_chord(self, mock_is_locked: MagicMock, mock_relock_verified: AsyncMock) -> None:
        assert await MacScreenUnlocker.ensure_locked() is True
        mock_relock_verified.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("verified", [True, False])
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)
    async def test_unlocked_delegates_to_verified_relock(self, mock_is_locked: MagicMock, verified: bool) -> None:
        with patch.object(MacScreenUnlocker, "relock_verified", new_callable=AsyncMock, return_value=verified) as relock:
            assert await MacScreenUnlocker.ensure_locked() is verified
        relock.assert_awaited_once()


class TestReleaseUnlockLease:
    @pytest.mark.asyncio
    async def test_bit_cleared_only_after_verified_lock(self, lease_bit: tuple[MagicMock, MagicMock]) -> None:
        _, clear = lease_bit
        with patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=True):
            assert await release_unlock_lease() is True
        clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_bit_kept_when_screen_cannot_be_locked(self, lease_bit: tuple[MagicMock, MagicMock]) -> None:
        _, clear = lease_bit
        with patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=False):
            assert await release_unlock_lease() is False
        clear.assert_not_called()


class TestLockedUseSession:
    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, return_value=True)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=True)
    async def test_mac_locked_enabled(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        mark, clear = lease_bit
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_called_once()
        mark.assert_called_once()
        mock_unlock.assert_called_once()
        mock_ensure_locked.assert_awaited_once()
        clear.assert_called_once()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=False)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock)
    async def test_mac_unlocked_enabled(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        mark, clear = lease_bit
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_called_once()
        mock_unlock.assert_not_called()
        mock_ensure_locked.assert_not_called()
        mark.assert_not_called()
        clear.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked")
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock)
    async def test_mac_disabled(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        config = LockedUseConfig(enabled=False)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_not_called()
        mock_unlock.assert_not_called()
        mock_ensure_locked.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Windows")
    @patch.object(MacScreenUnlocker, "is_locked")
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock)
    async def test_non_mac_enabled(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mock_sleep_inhibitor.assert_called_once_with(prevent_display_sleep=True)
        mock_is_locked.assert_not_called()
        mock_unlock.assert_not_called()
        mock_ensure_locked.assert_not_called()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, return_value=False)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=True)
    async def test_failed_unlock_still_hands_the_lease_back(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        """解锁失败（密码错/无密码）：租约位必须交还，否则帷幕滞留遮蔽。"""
        mark, clear = lease_bit
        config = LockedUseConfig(enabled=True)
        async with locked_use_session(config):
            pass

        mark.assert_called_once()
        mock_unlock.assert_called_once()
        mock_ensure_locked.assert_awaited_once()  # 屏幕仍锁：不发锁屏按键，只验证
        clear.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure", [asyncio.CancelledError(), RuntimeError("unlock exploded")])
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=True)
    async def test_cancelled_or_crashed_unlock_still_hands_the_lease_back(
        self,
        mock_ensure_locked: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        failure: BaseException,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        """解锁途中被取消/崩溃：键入可能已生效，必须回锁校验并交还租约位。"""
        _, clear = lease_bit
        with (
            patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, side_effect=failure),
            pytest.raises(type(failure)),
        ):
            async with locked_use_session(LockedUseConfig(enabled=True)):
                pytest.fail("session body must not run when unlock raised")

        mock_ensure_locked.assert_awaited_once()
        clear.assert_called_once()

    @pytest.mark.asyncio
    @patch("platform.system", return_value="Darwin")
    @patch.object(MacScreenUnlocker, "is_locked", return_value=True)
    @patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock, return_value=True)
    @patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=False)
    async def test_mac_locked_relock_failure_keeps_curtain_lease(
        self,
        mock_ensure_locked: MagicMock,
        mock_unlock: MagicMock,
        mock_is_locked: MagicMock,
        mock_system: MagicMock,
        mock_sleep_inhibitor: MagicMock,
        lease_bit: tuple[MagicMock, MagicMock],
    ) -> None:
        """回锁失败时不得交还帷幕租约（屏幕需保持遮蔽）。"""
        _, clear = lease_bit
        async with locked_use_session(LockedUseConfig(enabled=True)):
            pass

        mock_ensure_locked.assert_awaited_once()
        clear.assert_not_called()
