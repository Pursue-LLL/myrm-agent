"""无人值守帷幕获取单测 — 五条件代解锁租约获取分支与 watcher 生命周期。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 编排逻辑）
- tests.support.curtain_watcher（POS: 状态快照与 tick 驱动器）

[OUTPUT]
- 获取分支覆盖：无状态文件、未锁定重置计数、超限暂停、静默未满、
  CU 会话不活跃、租约位落盘失败、解锁成功/失败、异常吞掉
- start_unattended_curtain_watcher 幂等断言

[POS]
与 test_unattended_lease.py（租约持有/交还/作废/接管）互补。纯 mock 无真实解锁，
tick 循环经哨兵异常退出，不真 sleep，恒定 CPU/内存消耗（电脑性能受限环境下安全）。
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    MAX_UNLOCK_ATTEMPTS,
    CurtainBridgeState,
)
from app.services.locked_use.service import MacScreenUnlocker
from tests.support.curtain_watcher import (
    drive,
    has_session,
    make_state,
    no_session,
    record_clear,
    set_locked,
)


def test_lease_acquired_and_bit_cleared_on_unlock_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """解锁失败：立即清除租约位（否则帷幕滞留遮蔽）。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: True)
    cleared = record_clear(monkeypatch)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(return_value=False))

    drive(monkeypatch)

    assert cleared == [True]
    assert unattended._lease_held is False
    assert unattended._unlock_failures == 1


def test_lease_acquired_on_successful_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """五条件齐备且解锁成功：进入租约持有态。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: True)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(return_value=True))

    drive(monkeypatch)

    assert unattended._lease_held is True


def test_state_file_absent_skips_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """非桌面端部署（无状态桥文件）：read → None，tick 静默空转。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: None)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    unlock.assert_not_awaited()


def test_inactive_curtain_skips_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """帷幕未拉起：不进入代解锁分支（解锁只为在跑的帷幕任务服务）。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(active=False))
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    unlock.assert_not_awaited()


def test_user_unlock_resets_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """屏幕已解锁 = 用户在场证明：重置连续失败计数，恢复编排能力。"""
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, False)

    drive(monkeypatch)

    assert unattended._unlock_failures == 0


def test_failure_limit_pauses_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码错误达上限：暂停代解锁（Guardian 锁屏拒答兜底），不再重复尝试。"""
    mark = MagicMock()
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    mark.assert_not_called()
    unlock.assert_not_awaited()


def test_quiet_period_not_elapsed_skips_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """静默期未满：最近有物理输入（可能有人在场），不代解锁。"""
    mark = MagicMock()
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(quiet_elapsed=False))
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    unlock.assert_not_awaited()


def test_no_active_cu_session_skips_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """无活跃 CU 会话：解锁只为在跑的任务服务，无任务不解锁。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", no_session)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    unlock.assert_not_awaited()


def test_pending_write_failure_aborts_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """pending 落盘失败：必须放弃解锁（否则 Tauri 按用户解锁收起帷幕裸奔）。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: False)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch)

    unlock.assert_not_awaited()


def test_successful_unlock_resets_count_and_audits(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """五条件齐备 → pending 先落盘再解锁；成功重置计数并审计。"""
    order: list[str] = []

    async def _unlock() -> bool:
        order.append("unlock")
        return True

    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)

    def _mark_pending() -> bool:
        order.append("pending")
        return True

    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", _mark_pending)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(side_effect=_unlock))
    monkeypatch.setattr(unattended, "_unlock_failures", 2)

    with caplog.at_level(logging.INFO):
        drive(monkeypatch)

    assert order == ["pending", "unlock"]
    assert unattended._unlock_failures == 0
    assert "unattended unlock granted" in caplog.text


def test_failed_unlock_increments_count(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """解锁失败：计数 +1 并记录错误（供上限门控暂停编排）。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: True)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(return_value=False))

    with caplog.at_level(logging.ERROR):
        drive(monkeypatch)

    assert unattended._unlock_failures == 1
    assert "unattended unlock attempt failed" in caplog.text


def test_tick_exception_is_swallowed(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """watcher 必须永不退出：单 tick 异常被记录后继续下一轮。"""
    calls = {"count": 0}

    def _read() -> CurtainBridgeState | None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("bridge exploded")
        return None

    monkeypatch.setattr(unattended, "read_curtain_state", _read)

    with caplog.at_level(logging.WARNING):
        drive(monkeypatch, ticks=2)

    assert "tick failed" in caplog.text


def test_start_watcher_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """lifespan 重复调用不重建 task（幂等启动）。"""
    live_task = MagicMock()
    live_task.done.return_value = False
    created: list[str | None] = []

    def _create_task(coro: object, name: str | None = None) -> MagicMock:
        created.append(name)
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        return live_task

    adopted: list[bool] = []
    monkeypatch.setattr(unattended, "_watcher_task", None)
    monkeypatch.setattr(unattended, "_adopt_orphaned_lease", lambda: adopted.append(True))
    monkeypatch.setattr(asyncio, "create_task", _create_task)

    unattended.start_unattended_curtain_watcher()
    unattended.start_unattended_curtain_watcher()

    assert created == ["unattended-curtain-watcher"]
    assert adopted == [True]  # 仅首次启动接管遗留租约位
