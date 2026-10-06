"""harness 会话与帷幕编排的接线单测 — 真实 Guardian 经 attach_desktop_session 回调真实的按需解锁。

[INPUT]
- app.services.locked_use.unattended（POS: attach_desktop_session / unlock_screen_on_demand）
- myrm_agent_harness.toolkits.computer_use.ComputerSession（POS: 持有锁屏 Guardian 的 CU 会话）
- tests.support.curtain_watcher（POS: 状态快照与桩）

[OUTPUT]
- 接线后锁屏态下的物理输入先触发按需解锁，屏幕解开后该输入照常落地
- 门禁拒绝解锁时 Guardian 照常拒答，输入不落地

[POS]
tool_setup 的装配测试只证明「回调被注册」；本文件让真实会话走完整条链路，证明注册的回调
确实能让真实 Guardian 放行——harness 的回调协议与 server 函数签名在此处互相印证。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.computer_use.backends.protocols import ComputerBackend
from myrm_agent_harness.toolkits.computer_use.safety import ScreenLockedInterruptionError
from myrm_agent_harness.toolkits.computer_use.session import ComputerSession
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ComputerUseConfig

from app.services.locked_use import unattended
from tests.support.curtain_watcher import arm_on_demand_unlock, mark_watcher_running


def _locked_backend() -> MagicMock:
    backend = MagicMock(spec=ComputerBackend)
    backend.is_screen_locked.return_value = True
    backend.is_display_asleep.return_value = False
    backend.type_text = AsyncMock(return_value=ActionResult(success=True))
    return backend


def _attached_session(backend: MagicMock, monkeypatch: pytest.MonkeyPatch) -> ComputerSession:
    session = ComputerSession(backend=backend, config=ComputerUseConfig(screenshot_delay=0.0))
    monkeypatch.setattr(session, "take_screenshot", AsyncMock(return_value=ActionResult(success=True)))
    unattended.attach_desktop_session(session)
    return session


class TestAttachedSessionOnDemandUnlock:
    async def test_locked_screen_is_unlocked_then_the_input_lands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _locked_backend()
        session = _attached_session(backend, monkeypatch)

        async def _unlock() -> bool:
            backend.is_screen_locked.return_value = False
            return True

        arm_on_demand_unlock(monkeypatch).side_effect = _unlock
        mark_watcher_running(monkeypatch)

        result = await session.type_text("hello")

        assert result.success is True
        backend.type_text.assert_awaited_once()
        assert unattended._lease_held is True

    async def test_a_gate_that_refuses_keeps_the_input_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = _locked_backend()
        session = _attached_session(backend, monkeypatch)
        unlock = arm_on_demand_unlock(monkeypatch)
        mark_watcher_running(monkeypatch)
        monkeypatch.setenv("MYRM_LOCKED_USE_ENABLED", "false")

        with pytest.raises(ScreenLockedInterruptionError):
            await session.type_text("secret")

        unlock.assert_not_awaited()
        backend.type_text.assert_not_awaited()
        assert unattended._lease_held is False
