"""无人值守帷幕编排单测 — 五条件代解锁状态机。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 编排逻辑）
- app.services.locked_use.curtain_bridge.CurtainBridgeState（POS: 状态桥快照）

[OUTPUT]
- tick 分支覆盖：无状态文件、活跃边沿广播、未锁定重置计数、超限暂停、
  静默未满、CU 会话不活跃、pending 落盘失败、解锁成功/失败、异常吞掉
- start_unattended_curtain_watcher 幂等断言

[POS]
纯 mock 无真实解锁与事件总线；tick 循环经哨兵异常退出，不真 sleep，
恒定 CPU/内存消耗（电脑性能受限环境下安全）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    MAX_UNLOCK_ATTEMPTS,
    QUIET_PERIOD_SECONDS,
    CurtainBridgeState,
)
from app.services.locked_use.service import MacScreenUnlocker


class _StopLoop(BaseException):
    """哨兵：第 ``max_ticks + 1`` 次 sleep 抛出，让无限 tick 循环可测地退出。

    继承 BaseException 以免被 ``_watch_loop`` 的 ``except Exception`` 吞掉。
    """


@pytest.fixture(autouse=True)
def _reset_watcher_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例重置模块级计数器与广播边沿，避免用例间串扰。"""
    monkeypatch.setattr(unattended, "_unlock_failures", 0)
    monkeypatch.setattr(unattended, "_last_published_active", None)


def _state(
    *,
    active: bool = True,
    auto_engaged: bool = True,
    pending_auto_unlock: bool = False,
    quiet_elapsed: bool = True,
) -> CurtainBridgeState:
    """构造状态快照；``quiet_elapsed`` 决定静默期门控是否放行。"""
    now_ms = int(time.time() * 1000)
    offset_ms = -int(QUIET_PERIOD_SECONDS * 1000) - 1_000 if quiet_elapsed else -1_000
    return CurtainBridgeState(
        active=active,
        auto_engaged=auto_engaged,
        last_physical_input_ms=now_ms + offset_ms,
        pending_auto_unlock=pending_auto_unlock,
    )


def _drive(monkeypatch: pytest.MonkeyPatch, ticks: int = 1) -> None:
    """跑 ``_watch_loop`` 的 ``ticks`` 个 tick 后以哨兵退出（不真 sleep）。"""
    calls = {"count": 0}

    async def _fake_sleep(_seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] > ticks:
            raise _StopLoop

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    with pytest.raises(_StopLoop):
        asyncio.run(unattended._watch_loop())


async def _no_session() -> bool:
    return False


async def _has_session() -> bool:
    return True


def _locked(monkeypatch: pytest.MonkeyPatch, locked: bool) -> None:
    monkeypatch.setattr(MacScreenUnlocker, "is_locked", staticmethod(lambda: locked))


def test_state_file_absent_skips_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """非桌面端部署（无状态桥文件）：read → None，tick 静默空转。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: None)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    unlock.assert_not_awaited()


def test_first_active_tick_publishes_edge(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """活跃态边沿：首次观测 active=True 时广播一次（移动端看板回执）。"""
    published: list[CurtainBridgeState] = []
    unique = _state(active=True, auto_engaged=True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: unique)
    monkeypatch.setattr(unattended, "_publish_state_change", published.append)
    monkeypatch.setattr(unattended, "_cu_session_active", _no_session)

    _drive(monkeypatch)

    assert published == [unique]
    assert published[0].active is True
    assert published[0].auto_engaged is True


def test_steady_active_state_is_not_rebroadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    """活跃态未变时不重复广播（避免 SSE 流噪音）。"""
    published: list[CurtainBridgeState] = []
    monkeypatch.setattr(unattended, "_last_published_active", True)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state(active=True))
    monkeypatch.setattr(unattended, "_publish_state_change", published.append)
    monkeypatch.setattr(unattended, "_cu_session_active", _no_session)

    _drive(monkeypatch, ticks=2)

    assert published == []


def test_inactive_curtain_skips_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """帷幕未拉起：不进入代解锁分支（解锁只为在跑的帷幕任务服务）。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state(active=False))
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    unlock.assert_not_awaited()


def test_user_unlock_resets_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """屏幕已解锁 = 用户在场证明：重置连续失败计数，恢复编排能力。"""
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, False)

    _drive(monkeypatch)

    assert unattended._unlock_failures == 0


def test_failure_limit_pauses_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """密码错误达上限：暂停代解锁（Guardian 锁屏拒答兜底），不再重复尝试。"""
    mark = MagicMock()
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    mark.assert_not_called()
    unlock.assert_not_awaited()


def test_quiet_period_not_elapsed_skips_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """静默期未满：最近有物理输入（可能有人在场），不代解锁。"""
    mark = MagicMock()
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state(quiet_elapsed=False))
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    unlock.assert_not_awaited()


def test_no_active_cu_session_skips_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """无活跃 CU 会话：解锁只为在跑的任务服务，无任务不解锁。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", _no_session)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    unlock.assert_not_awaited()


def test_pending_write_failure_aborts_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """pending 落盘失败：必须放弃解锁（否则 Tauri 按用户解锁收起帷幕裸奔）。"""
    unlock = AsyncMock()
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", _has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: False)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

    _drive(monkeypatch)

    unlock.assert_not_awaited()


def test_successful_unlock_resets_count_and_audits(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """五条件齐备 → pending 先落盘再解锁；成功重置计数并审计。"""
    order: list[str] = []

    async def _unlock() -> bool:
        order.append("unlock")
        return True

    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", _has_session)

    def _mark_pending() -> bool:
        order.append("pending")
        return True

    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", _mark_pending)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(side_effect=_unlock))
    monkeypatch.setattr(unattended, "_unlock_failures", 2)

    with caplog.at_level(logging.INFO):
        _drive(monkeypatch)

    assert order == ["pending", "unlock"]
    assert unattended._unlock_failures == 0
    assert "unattended unlock granted" in caplog.text


def test_failed_unlock_increments_count(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """解锁失败：计数 +1 并记录错误（供上限门控暂停编排）。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: _state())
    monkeypatch.setattr(unattended, "_publish_state_change", MagicMock())
    _locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "_cu_session_active", _has_session)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: True)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(return_value=False))

    with caplog.at_level(logging.ERROR):
        _drive(monkeypatch)

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
        _drive(monkeypatch, ticks=2)

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

    monkeypatch.setattr(unattended, "_watcher_task", None)
    monkeypatch.setattr(asyncio, "create_task", _create_task)

    unattended.start_unattended_curtain_watcher()
    unattended.start_unattended_curtain_watcher()

    assert created == ["unattended-curtain-watcher"]
