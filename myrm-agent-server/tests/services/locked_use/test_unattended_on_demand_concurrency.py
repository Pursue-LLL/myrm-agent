"""按需代解锁并发单测 — 单飞、有界等待、取消语义与交还/关闭期的串行。

[INPUT]
- app.services.locked_use.unattended（POS: unlock_screen_on_demand / 租约编排）
- tests.support.curtain_watcher（POS: 状态快照与桩）

[OUTPUT]
- 单飞：并发调用共享一次键入，第二轮密码不会落进已解锁的桌面
- 有界等待：超时只放弃等待，获取照常收尾；调用方被取消不取消获取
- 获取等在途交还收尾；关闭期等在途获取走完再回锁

[POS]
与 test_unattended_on_demand.py（获取门禁）互补。纯 mock 无真实解锁，并发场景以事件门控而非
真实耗时驱动。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.service import MacScreenUnlocker, UnlockAttemptOutcome
from tests.support.curtain_watcher import arm_on_demand_unlock, mark_watcher_running, record_clear


class _GatedUnlock:
    """可由测试放行的代解锁：``started`` 表示键入已开始，``release`` 前一直悬停。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self) -> UnlockAttemptOutcome:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return UnlockAttemptOutcome.SUCCESS


class TestConcurrency:
    async def test_concurrent_callers_share_one_typing_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """并发的 CU 工具调用共享同一次获取：第二轮密码键入不得落进已解锁的桌面。"""
        arm_on_demand_unlock(monkeypatch)
        mark_watcher_running(monkeypatch)
        typing = _GatedUnlock()
        monkeypatch.setattr(MacScreenUnlocker, "unlock", typing)

        first = asyncio.create_task(unattended.unlock_screen_on_demand())
        await typing.started.wait()
        second = asyncio.create_task(unattended.unlock_screen_on_demand())
        await asyncio.sleep(0)
        typing.release.set()
        await asyncio.gather(first, second)

        assert typing.calls == 1
        assert unattended._lease_held is True

    async def test_timeout_abandons_the_wait_but_not_the_acquisition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """有界等待：键入迟迟不结束时工具调用先放行（维持拒答），获取仍跑完并保持租约状态自洽。"""
        arm_on_demand_unlock(monkeypatch)
        mark_watcher_running(monkeypatch)
        monkeypatch.setattr(unattended, "ON_DEMAND_WAIT_SECONDS", 0.05)
        typing = _GatedUnlock()
        monkeypatch.setattr(MacScreenUnlocker, "unlock", typing)

        await unattended.unlock_screen_on_demand()

        assert unattended._lease_held is False
        pending = unattended._acquire_task
        assert pending is not None
        assert not pending.done()
        typing.release.set()
        await pending
        assert unattended._lease_held is True

    async def test_caller_cancellation_does_not_cancel_the_acquisition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """用户中止运行（调用方被取消）：已派出的键入照常收尾，租约交给 watcher 监护。"""
        arm_on_demand_unlock(monkeypatch)
        mark_watcher_running(monkeypatch)
        typing = _GatedUnlock()
        monkeypatch.setattr(MacScreenUnlocker, "unlock", typing)

        caller = asyncio.create_task(unattended.unlock_screen_on_demand())
        await typing.started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller

        pending = unattended._acquire_task
        assert pending is not None
        assert not pending.done()
        typing.release.set()
        await pending
        assert unattended._lease_held is True

    async def test_acquisition_waits_for_an_in_flight_release(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """交还中途发起的获取必须等回锁收尾，否则交还尾部会清掉刚置下的新租约位。"""
        order: list[str] = []
        release_started = asyncio.Event()
        release_gate = asyncio.Event()

        async def _release() -> bool:
            release_started.set()
            await release_gate.wait()
            order.append("released")
            return True

        async def _unlock() -> UnlockAttemptOutcome:
            order.append("unlock")
            return UnlockAttemptOutcome.SUCCESS

        arm_on_demand_unlock(monkeypatch)
        mark_watcher_running(monkeypatch)
        monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(side_effect=_unlock))
        monkeypatch.setattr(unattended, "release_unlock_lease", AsyncMock(side_effect=_release))
        monkeypatch.setattr(unattended, "_lease_held", True)
        cleared = record_clear(monkeypatch)

        releasing = asyncio.create_task(unattended._release_lease())
        await release_started.wait()
        caller = asyncio.create_task(unattended.unlock_screen_on_demand())
        await asyncio.sleep(0.01)
        assert order == []

        release_gate.set()
        await asyncio.gather(releasing, caller)

        assert order == ["released", "unlock"]
        assert cleared == []
        assert unattended._lease_held is True

    async def test_shutdown_lets_an_in_flight_acquisition_settle_before_relocking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关闭期：已派出的键入取消不掉，先等它走完再回锁，屏幕不会在无人看管时解锁。"""
        order: list[str] = []
        typing = _GatedUnlock()

        async def _unlock() -> UnlockAttemptOutcome:
            order.append("unlock-start")
            result = await typing()
            order.append("unlock-done")
            return result

        async def _release() -> bool:
            order.append("release")
            return True

        arm_on_demand_unlock(monkeypatch)
        monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(side_effect=_unlock))
        monkeypatch.setattr(unattended, "release_unlock_lease", AsyncMock(side_effect=_release))
        monkeypatch.setattr(unattended, "_watcher_task", asyncio.create_task(asyncio.sleep(3600)))

        caller = asyncio.create_task(unattended.unlock_screen_on_demand())
        await typing.started.wait()
        stopping = asyncio.create_task(unattended.stop_unattended_curtain_watcher())
        await asyncio.sleep(0.01)
        assert order == ["unlock-start"]

        typing.release.set()
        await asyncio.gather(caller, stopping)

        assert order == ["unlock-start", "unlock-done", "release"]
        assert unattended._lease_held is False
