"""Tests for the re-lock chain and the unlock lease hand-back.

[INPUT]
- app.services.locked_use.service（POS: relock_verified / ensure_locked / release_unlock_lease）

[OUTPUT]
- 校验回锁（请求已发 ≠ 确已锁定）与租约交还门禁断言

[POS]
与 test_service.py（探测 / 解锁原语）互补：本文件覆盖回锁校验与租约交还。
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.locked_use.service import (
    MacScreenUnlocker,
    release_unlock_lease,
)


@pytest.fixture
def clear_lease() -> Iterator[MagicMock]:
    """隔离租约位文件写入：返回「清除租约位」探针。"""
    with patch("app.services.locked_use.service.clear_pending_auto_unlock") as clear:
        yield clear


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
    async def test_bit_cleared_only_after_verified_lock(self, clear_lease: MagicMock) -> None:
        with patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=True):
            assert await release_unlock_lease() is True
        clear_lease.assert_called_once()

    @pytest.mark.asyncio
    async def test_bit_kept_when_screen_cannot_be_locked(self, clear_lease: MagicMock) -> None:
        with patch.object(MacScreenUnlocker, "ensure_locked", new_callable=AsyncMock, return_value=False):
            assert await release_unlock_lease() is False
        clear_lease.assert_not_called()
