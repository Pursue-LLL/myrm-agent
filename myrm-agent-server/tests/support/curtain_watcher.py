"""无人值守帷幕 watcher 测试的共享支撑：状态快照构造、tick 驱动器与桩。

[INPUT]
- app.services.locked_use.unattended（POS: watcher 编排）
- app.services.locked_use.service（POS: 解锁原语与硬件输入空闲探针入口）
- app.services.locked_use.curtain_bridge.CurtainBridgeState（POS: 状态桥快照）

[OUTPUT]
- make_state / drive / acquire / mark_watcher_running / record_clear / set_locked / set_hid_idle / has_session / no_session / StopLoop
- AWAY_IDLE_SECONDS（主人离开已久的硬件输入空闲读数）
- dead_process_pid（已退出并被回收的进程 PID，模拟壳崩溃）

[POS]
test_unattended_on_demand.py（按需获取）、test_unattended_curtain_watcher.py（watcher 循环）与
test_unattended_lease.py（租约分支）共用；纯 mock，tick 循环经哨兵异常退出，不真 sleep。
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from unittest.mock import MagicMock

import pytest

from app.services.locked_use import service, unattended
from app.services.locked_use.curtain_bridge import (
    QUIET_PERIOD_SECONDS,
    CurtainBridgeState,
)
from app.services.locked_use.service import MacScreenUnlocker

# 主人离开已久（一小时）：远超任何合理的在场阈值。
AWAY_IDLE_SECONDS = 3600.0


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
    shell_alive: bool = True,
) -> CurtainBridgeState:
    """构造状态快照；``quiet_elapsed`` 决定静默期门控是否放行。

    ``shell_alive=False`` 模拟壳失联：与读侧一致，有效 ``active`` 随之为 False。
    """
    now_ms = int(time.time() * 1000)
    offset_ms = -int(QUIET_PERIOD_SECONDS * 1000) - 1_000 if quiet_elapsed else -1_000
    return CurtainBridgeState(
        active=active and shell_alive,
        auto_engaged=auto_engaged,
        last_physical_input_ms=now_ms + offset_ms,
        pending_auto_unlock=pending_auto_unlock,
        shell_alive=shell_alive,
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


def mark_watcher_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """令按需解锁的受理前提（watcher 在运行）成立，而不真启动 watcher 循环。"""
    live_watcher = MagicMock()
    live_watcher.done.return_value = False
    monkeypatch.setattr(unattended, "_watcher_task", live_watcher)


def acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    """以「watcher 运行中」为前提跑一次按需解锁（harness Guardian 撞上锁屏时的回调）。"""
    mark_watcher_running(monkeypatch)
    asyncio.run(unattended.unlock_screen_on_demand())


def dead_process_pid() -> int:
    """启动一个立即退出并被回收的子进程，返回其已不存在的 PID（模拟壳崩溃 / 被强杀）。"""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


async def no_session() -> bool:
    return False


async def has_session() -> bool:
    return True


def set_locked(monkeypatch: pytest.MonkeyPatch, locked: bool) -> None:
    monkeypatch.setattr(MacScreenUnlocker, "is_locked", staticmethod(lambda: locked))


def set_hid_idle(monkeypatch: pytest.MonkeyPatch, seconds: float | None) -> None:
    """令硬件输入空闲探针返回 ``seconds``（``None`` = 探测失败）。

    真实探针读的是开发机此刻的键鼠状态，用例必须经此固定，结果才不随人是否在敲键盘而变。
    """
    monkeypatch.setattr(service, "hid_idle_seconds", lambda: seconds)
