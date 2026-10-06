"""无人值守帷幕 watcher 循环单测 — 不自行获取租约、失败计数复位、异常自愈、幂等启动。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 循环）
- tests.support.curtain_watcher（POS: 状态快照与 tick 驱动器）

[OUTPUT]
- watcher 循环不自行获取租约：锁屏 + 帷幕 + 会话活跃 + 静默期满 + 机前无人全齐，N 个 tick 后仍不解锁
  （唯一的获取触发点是 Guardian 的按需回调）
- 用户亲自解锁（在场证明）重置失败计数；仍锁屏时计数保持
- 单 tick 异常被吞掉后继续下一轮
- start_unattended_curtain_watcher 幂等断言

[POS]
与 test_unattended_on_demand.py（按需获取）和 test_unattended_lease.py（租约持有/交还）互补。
纯 mock，tick 循环经哨兵异常退出，不真 sleep，恒定 CPU/内存消耗（电脑性能受限环境下安全）。
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import MAX_UNLOCK_ATTEMPTS, CurtainBridgeState
from app.services.locked_use.service import MacScreenUnlocker
from tests.support.curtain_watcher import drive, has_session, make_state, set_locked


def test_loop_never_acquires_a_lease_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有解锁条件齐备时 watcher 也只监护不获取：纯文本任务不得因「有会话」被解锁折腾。"""
    mark = MagicMock(return_value=True)
    unlock = AsyncMock(return_value=True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    drive(monkeypatch, ticks=3)

    mark.assert_not_called()
    unlock.assert_not_awaited()
    assert unattended._lease_held is False


def test_user_unlock_resets_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """屏幕已解锁 = 用户在场证明：重置连续失败计数，恢复编排能力。"""
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, False)

    drive(monkeypatch)

    assert unattended._unlock_failures == 0


def test_failure_count_is_kept_while_the_screen_stays_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """仍锁屏就没有在场证明：失败计数保持，暂停不会被 watcher 悄悄解除。"""
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)

    drive(monkeypatch, ticks=2)

    assert unattended._unlock_failures == MAX_UNLOCK_ATTEMPTS


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
