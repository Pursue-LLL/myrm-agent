"""harness 会话与帷幕编排的接线单测 — 真实 Guardian 经 attach_desktop_session 回调真实的按需解锁，
帷幕窗口 title 经真实后端链送达截图后端。

[INPUT]
- app.services.locked_use.unattended（POS: attach_desktop_session / unlock_screen_on_demand）
- app.services.locked_use.curtain_bridge.EXCLUDED_CAPTURE_TITLES（POS: 与 Tauri 帷幕窗口 title 的契约）
- myrm_agent_harness.toolkits.computer_use.ComputerSession / DesktopSession（POS: 持有锁屏 Guardian 的 CU 会话）
- myrm_agent_harness.toolkits.computer_use.backends（POS: 生产桌面后端链 CuaDriverBackend → MacOSBackend）
- tests.support.curtain_watcher（POS: 状态快照与桩）

[OUTPUT]
- 接线后锁屏态下的物理输入先触发按需解锁，屏幕解开后该输入照常落地
- 门禁拒绝解锁时 Guardian 照常拒答，输入不落地
- 帷幕窗口 title 穿过 CuaDriver 包装链落到原生截图后端；排除通道缺失时仅在 macOS 记 WARNING

[POS]
tool_setup 的装配测试只证明「回调被注册」；本文件让真实会话走完整条链路，证明注册的回调
确实能让真实 Guardian 放行——harness 的回调协议与 server 函数签名在此处互相印证。
排除通道同理：harness 侧单测证明后端链被正确解析，本文件证明 server 交出的正是契约 title。
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.computer_use.backends.cua_driver import CuaDriverBackend
from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
from myrm_agent_harness.toolkits.computer_use.backends.protocols import ComputerBackend
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession
from myrm_agent_harness.toolkits.computer_use.safety import ScreenLockedInterruptionError
from myrm_agent_harness.toolkits.computer_use.session import ComputerSession
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ComputerUseConfig

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import EXCLUDED_CAPTURE_TITLES
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


class TestAttachedSessionCaptureExclusion:
    def test_the_curtain_title_reaches_the_backend_behind_cua_driver(self) -> None:
        """生产桌面后端链：cua-driver 自己不截屏，帷幕 title 必须落到它包着的原生后端。"""
        native = MacOSBackend()
        session = DesktopSession(backend=CuaDriverBackend(fallback=native))

        assert unattended.attach_desktop_session(session) is True
        assert native._excluded_capture_titles == frozenset(EXCLUDED_CAPTURE_TITLES)

    @pytest.mark.parametrize(
        ("system", "warns"),
        [("Darwin", True), ("Linux", False), ("Windows", False)],
    )
    def test_a_missing_channel_warns_only_where_the_capability_exists(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        system: str,
        warns: bool,
    ) -> None:
        """非 macOS 没有该能力是设计内降级，静默；macOS 上缺失意味着后端链回归，必须可见。"""
        session = ComputerSession(backend=MagicMock(spec=ComputerBackend))
        monkeypatch.setattr(unattended.platform, "system", lambda: system)

        with caplog.at_level(logging.WARNING, logger=unattended.logger.name):
            assert unattended.attach_desktop_session(session) is False

        assert any("Capture exclusion is unavailable" in record.getMessage() for record in caplog.records) is warns
