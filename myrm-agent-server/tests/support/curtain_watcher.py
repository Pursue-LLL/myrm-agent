"""无人值守帷幕 watcher 测试的共享支撑：状态快照构造、tick 驱动器与桩。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 编排）
- app.services.locked_use.curtain_bridge.CurtainBridgeState（POS: 状态桥快照）

[OUTPUT]
- make_state / drive / record_clear / set_locked / has_session / no_session / StopLoop

[POS]
test_unattended_curtain_watcher.py（获取分支）与 test_unattended_lease.py（租约分支）共用；
纯 mock，tick 循环经哨兵异常退出，不真 sleep。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    QUIET_PERIOD_SECONDS,
    CurtainBridgeState,
)
from app.services.locked_use.service import MacScreenUnlocker


class StopLoop(BaseException):
    """哨兵：第 ``max_ticks + 1`` 次 sleep 抛出，让无限 tick 循环可测地退出。

    继承 BaseException 以免被 ``_watch_loop`` 的 ``except Exception`` 吞掉。
    """


def make_state(
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


def record_clear(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """用记录器替换租约位清除；返回的列表每被清除一次追加一项。"""
    cleared: list[bool] = []

    def _clear() -> bool:
        cleared.append(True)
        return True

    monkeypatch.setattr(unattended, "clear_pending_auto_unlock", _clear)
    return cleared


def drive(monkeypatch: pytest.MonkeyPatch, ticks: int = 1) -> None:
    """跑 ``_watch_loop`` 的 ``ticks`` 个 tick 后以哨兵退出（不真 sleep）。"""
    calls = {"count": 0}

    async def _fake_sleep(_seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] > ticks:
            raise StopLoop

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    with pytest.raises(StopLoop):
        asyncio.run(unattended._watch_loop())


async def no_session() -> bool:
    return False


async def has_session() -> bool:
    return True


def set_locked(monkeypatch: pytest.MonkeyPatch, locked: bool) -> None:
    monkeypatch.setattr(MacScreenUnlocker, "is_locked", staticmethod(lambda: locked))
