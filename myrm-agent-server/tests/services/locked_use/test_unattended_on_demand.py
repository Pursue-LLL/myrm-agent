"""按需代解锁单测 — Guardian 撞上锁屏时的五条件租约获取、单飞与并发安全。

[INPUT]
- app.services.locked_use.unattended（POS: unlock_screen_on_demand / 租约编排）
- tests.support.curtain_watcher（POS: 状态快照与桩）

[OUTPUT]
- 五条件齐备才解锁：Locked Use 已授权、帷幕有效（含壳失联的真实读侧回归）、静默期满、
  重试未超限、机前无人；每个门禁都配阳性对照，证明「不解锁」出自该门禁
- 租约位先落盘再键入；失败/异常立即交还租约位；落盘失败放弃解锁
- 持租约期间屏幕被外部锁上：旧租约作废后重新获取
- watcher 未运行不受理（无人监护就不解锁）
- 单飞（并发调用共享一次键入）、有界等待（超时只放弃等待）、调用方取消不取消获取、
  获取等在途交还收尾、关闭期等在途获取走完再回锁

[POS]
与 test_unattended_curtain_watcher.py（watcher 循环）和 test_unattended_lease.py（租约持有/交还）
互补。纯 mock 无真实解锁，并发场景以事件门控而非真实耗时驱动。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import MAX_UNLOCK_ATTEMPTS, SHELL_PID_ENV
from app.services.locked_use.service import MacScreenUnlocker
from tests.support.curtain_watcher import (
    AWAY_IDLE_SECONDS,
    acquire,
    make_state,
    mark_watcher_running,
    record_clear,
    set_hid_idle,
    set_locked,
)


def _arm(monkeypatch: pytest.MonkeyPatch, *, unlocks: bool = True) -> AsyncMock:
    """五条件齐备的锁屏场景；返回代解锁桩（每个门禁用例只改动其中一个条件）。"""
    monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state())
    set_locked(monkeypatch, True)
    monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: True)
    unlock = AsyncMock(return_value=unlocks)
    monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)
    return unlock


class _GatedUnlock:
    """可由测试放行的代解锁：``started`` 表示键入已开始，``release`` 前一直悬停。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self) -> bool:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return True


class TestAcquisitionGates:
    def test_unlock_success_takes_the_lease_and_audits(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """五条件齐备：租约位先落盘再键入；成功重置失败计数并审计。"""
        order: list[str] = []

        def _mark_pending() -> bool:
            order.append("pending")
            return True

        async def _unlock() -> bool:
            order.append("unlock")
            return True

        _arm(monkeypatch)
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", _mark_pending)
        monkeypatch.setattr(MacScreenUnlocker, "unlock", AsyncMock(side_effect=_unlock))
        monkeypatch.setattr(unattended, "_unlock_failures", 2)

        with caplog.at_level(logging.INFO):
            acquire(monkeypatch)

        assert order == ["pending", "unlock"]
        assert unattended._lease_held is True
        assert unattended._unlock_failures == 0
        assert "unattended unlock granted" in caplog.text

    def test_unlock_failure_returns_the_bit_and_counts(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """解锁失败：立即交还租约位（否则帷幕滞留遮蔽）、计数 +1 并记录错误。"""
        _arm(monkeypatch, unlocks=False)
        cleared = record_clear(monkeypatch)

        with caplog.at_level(logging.ERROR):
            acquire(monkeypatch)

        assert cleared == [True]
        assert unattended._lease_held is False
        assert unattended._unlock_failures == 1
        assert "unattended unlock attempt failed" in caplog.text

    def test_unexpected_unlock_error_returns_the_bit_and_surfaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """键入前的意外异常：租约位照样交还，异常上抛给 Guardian（不算密码错误，不计失败）。"""
        unlock = _arm(monkeypatch)
        unlock.side_effect = OSError("caffeinate missing")
        cleared = record_clear(monkeypatch)

        with pytest.raises(OSError, match="caffeinate missing"):
            acquire(monkeypatch)

        assert cleared == [True]
        assert unattended._lease_held is False
        assert unattended._unlock_failures == 0

    def test_pending_write_failure_aborts_unlock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """租约位落盘失败：必须放弃解锁（否则 Tauri 按用户解锁收起帷幕裸奔）。"""
        unlock = _arm(monkeypatch)
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", lambda: False)

        acquire(monkeypatch)

        unlock.assert_not_awaited()
        assert unattended._lease_held is False

    def test_state_file_absent_never_unlocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非桌面端部署（无状态桥文件）：没有帷幕就没有解锁。"""
        unlock = _arm(monkeypatch)
        monkeypatch.setattr(unattended, "read_curtain_state", lambda: None)

        acquire(monkeypatch)

        unlock.assert_not_awaited()

    def test_inactive_curtain_never_unlocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """帷幕未拉起：解锁后屏幕无人遮蔽，一律不解锁。"""
        unlock = _arm(monkeypatch)
        monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(active=False))

        acquire(monkeypatch)

        unlock.assert_not_awaited()

    def test_gone_shell_never_acquires_a_lease(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """壳失联 = 没有帷幕在遮蔽：其余条件全齐也不置租约位、不代解锁。"""
        unlock = _arm(monkeypatch)
        mark = MagicMock()
        monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(shell_alive=False))
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)

        acquire(monkeypatch)

        mark.assert_not_called()
        unlock.assert_not_awaited()
        assert unattended._lease_held is False

    @pytest.mark.parametrize(("shell_is_alive", "expect_unlock"), [(True, True), (False, False)])
    def test_stale_state_file_of_a_gone_shell_never_unlocks(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        dead_shell_pid: int,
        shell_is_alive: bool,
        expect_unlock: bool,
    ) -> None:
        """回归：壳崩溃后状态文件仍写着 active:true。

        真实读侧 + 真实状态文件：没有壳就没有帷幕，绝不键入登录密码；壳存活的同款状态是
        阳性对照，证明「不解锁」的断言不是因为场景本身凑不齐条件而空转。
        """
        state_file = tmp_path / "curtain_state.json"
        state_file.write_text(
            json.dumps({"active": True, "autoEngaged": True, "lastPhysicalInputMs": 0, "pendingAutoUnlock": False}),
            encoding="utf-8",
        )
        monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(state_file))
        if not shell_is_alive:
            monkeypatch.setenv(SHELL_PID_ENV, str(dead_shell_pid))
        set_locked(monkeypatch, True)
        unlock = AsyncMock(return_value=True)
        monkeypatch.setattr(MacScreenUnlocker, "unlock", unlock)

        acquire(monkeypatch)

        assert (unlock.await_count == 1) is expect_unlock
        assert json.loads(state_file.read_text(encoding="utf-8"))["pendingAutoUnlock"] is expect_unlock

    @pytest.mark.parametrize("authorization", ["false", "", None])
    def test_unauthorized_locked_use_never_unlocks(self, monkeypatch: pytest.MonkeyPatch, authorization: str | None) -> None:
        """用户没有授权 Locked Use（关闭 / 空 / 未注入）：其余条件全齐也不置租约位、不代解锁。

        授权开启的同款场景由 test_unlock_success_takes_the_lease_and_audits 作阳性对照。
        """
        unlock = _arm(monkeypatch)
        mark = MagicMock()
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
        if authorization is None:
            monkeypatch.delenv("MYRM_LOCKED_USE_ENABLED")
        else:
            monkeypatch.setenv("MYRM_LOCKED_USE_ENABLED", authorization)

        acquire(monkeypatch)

        mark.assert_not_called()
        unlock.assert_not_awaited()

    def test_failure_limit_pauses_unlocking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """密码错误达上限：暂停代解锁（Guardian 锁屏拒答兜底），不再重复尝试。"""
        unlock = _arm(monkeypatch)
        mark = MagicMock()
        monkeypatch.setattr(unattended, "_unlock_failures", MAX_UNLOCK_ATTEMPTS)
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)

        acquire(monkeypatch)

        mark.assert_not_called()
        unlock.assert_not_awaited()

    def test_quiet_period_not_elapsed_never_unlocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """静默期未满：最近有物理输入（可能有人在场），不代解锁。"""
        unlock = _arm(monkeypatch)
        monkeypatch.setattr(unattended, "read_curtain_state", lambda: make_state(quiet_elapsed=False))

        acquire(monkeypatch)

        unlock.assert_not_awaited()

    @pytest.mark.parametrize(
        ("idle_seconds", "expect_unlock"),
        [(2.0, False), (None, False), (AWAY_IDLE_SECONDS, True)],
    )
    def test_user_at_the_machine_defers_the_lease(
        self, monkeypatch: pytest.MonkeyPatch, idle_seconds: float | None, expect_unlock: bool
    ) -> None:
        """机前有人（或无法判定）：其余条件全齐也不置租约位、不计失败、不键入。

        主人离开的同款状态是阳性对照，证明「不解锁」出自在场门禁而非场景凑不齐条件。
        """
        unlock = _arm(monkeypatch)
        mark = MagicMock(return_value=True)
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
        set_hid_idle(monkeypatch, idle_seconds)

        acquire(monkeypatch)

        assert (mark.call_count == 1) is expect_unlock
        assert (unlock.await_count == 1) is expect_unlock
        assert unattended._lease_held is expect_unlock
        assert unattended._unlock_failures == 0

    def test_deferred_acquisition_resumes_once_the_user_steps_away(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """人在场的那次获取整个放弃，输入停下后的下一次工具调用自然续跑（无需额外状态）。"""
        unlock = _arm(monkeypatch)
        set_hid_idle(monkeypatch, 2.0)
        acquire(monkeypatch)
        unlock.assert_not_awaited()

        set_hid_idle(monkeypatch, AWAY_IDLE_SECONDS)
        acquire(monkeypatch)

        unlock.assert_awaited_once()
        assert unattended._lease_held is True

    def test_lock_after_a_held_lease_voids_it_and_reacquires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """持租约期间屏幕被外部锁上（自动锁屏等）：旧租约作废，按同一套门禁重新获取。"""
        unlock = _arm(monkeypatch)
        monkeypatch.setattr(unattended, "_lease_held", True)
        cleared = record_clear(monkeypatch)

        acquire(monkeypatch)

        assert cleared == [True]
        unlock.assert_awaited_once()
        assert unattended._lease_held is True


class TestWatcherPrecondition:
    @pytest.mark.parametrize("watcher_state", ["never_started", "finished"])
    def test_unlock_is_declined_without_a_running_watcher(self, monkeypatch: pytest.MonkeyPatch, watcher_state: str) -> None:
        """没有 watcher 兜底（未启动 / 已停止）就不能解锁：租约无人监护与交还。"""
        unlock = _arm(monkeypatch)
        mark = MagicMock()
        monkeypatch.setattr(unattended, "mark_pending_auto_unlock", mark)
        if watcher_state == "finished":
            stopped = MagicMock()
            stopped.done.return_value = True
            monkeypatch.setattr(unattended, "_watcher_task", stopped)

        asyncio.run(unattended.unlock_screen_on_demand())

        mark.assert_not_called()
        unlock.assert_not_awaited()


class TestConcurrency:
    async def test_concurrent_callers_share_one_typing_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """并发的 CU 工具调用共享同一次获取：第二轮密码键入不得落进已解锁的桌面。"""
        _arm(monkeypatch)
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
        _arm(monkeypatch)
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
        _arm(monkeypatch)
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

        async def _unlock() -> bool:
            order.append("unlock")
            return True

        _arm(monkeypatch)
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

        async def _unlock() -> bool:
            order.append("unlock-start")
            result = await typing()
            order.append("unlock-done")
            return result

        async def _release() -> bool:
            order.append("release")
            return True

        _arm(monkeypatch)
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
