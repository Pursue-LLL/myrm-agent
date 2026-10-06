"""SleepInhibitor 引用计数单测 — 显示器常亮需求的独立计数。

[INPUT]
- app.services.infra.sleep_inhibitor.SleepInhibitor（POS: 引用计数休眠抑制）

[OUTPUT]
- 普通 hold 先占位时 CU 显示器需求仍能升级；最后一位显示器持有者退出后降级；
  全部退出后释放；非本地模式 no-op

[POS]
纯 mock（不触碰真实 IOKit/systemd/windll）：仅验证引用计数与升级/降级状态机。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.infra.sleep_inhibitor import SleepInhibitor


@pytest.fixture(autouse=True)
def _reset_inhibitor_state() -> None:
    """重置类级计数，避免用例间串扰。"""
    SleepInhibitor._ref_count = 0
    SleepInhibitor._display_ref_count = 0
    SleepInhibitor._display_active = False
    SleepInhibitor._process = None
    SleepInhibitor._prev_exec_state = None


@pytest.fixture(autouse=True)
def _local_mode() -> object:
    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        yield


@pytest.mark.asyncio()
async def test_single_display_hold_activates_display_assertion() -> None:
    activate = MagicMock()
    with patch.object(SleepInhibitor, "_activate", activate), patch.object(SleepInhibitor, "_deactivate", MagicMock()):
        async with SleepInhibitor.hold(prevent_display_sleep=True):
            pass

    activate.assert_called_once_with(prevent_display_sleep=True)
    assert SleepInhibitor._display_active is False


@pytest.mark.asyncio()
async def test_display_requirement_upgrades_after_plain_hold() -> None:
    """普通 hold 先占位时，后到的 CU 显示器需求必须升级而非被吞掉。"""
    activate = MagicMock()
    deactivate = MagicMock()
    with patch.object(SleepInhibitor, "_activate", activate), patch.object(SleepInhibitor, "_deactivate", deactivate):
        async with SleepInhibitor.hold():
            async with SleepInhibitor.hold(prevent_display_sleep=True):
                assert SleepInhibitor._display_active is True

    # 初始普通 → 升级为常亮 → 最后一位显示器持有者退出后降级回普通。
    assert [call.kwargs.get("prevent_display_sleep") for call in activate.call_args_list] == [
        False,
        True,
        False,
    ]
    # 升级、降级、最终释放各一次。
    assert deactivate.call_count == 3


@pytest.mark.asyncio()
async def test_display_stays_active_while_another_display_holder_remains() -> None:
    """仍有其他显示器持有者时需要保持常亮，不得提前降级。"""
    activate = MagicMock()
    deactivate = MagicMock()
    with patch.object(SleepInhibitor, "_activate", activate), patch.object(SleepInhibitor, "_deactivate", deactivate):
        async with SleepInhibitor.hold(prevent_display_sleep=True):
            async with SleepInhibitor.hold(prevent_display_sleep=True):
                assert SleepInhibitor._display_ref_count == 2
            assert SleepInhibitor._display_active is True
            assert deactivate.call_count == 0

    activate.assert_called_once()
    deactivate.assert_called_once()


@pytest.mark.asyncio()
async def test_releases_when_all_holders_exit() -> None:
    activate = MagicMock()
    deactivate = MagicMock()
    with patch.object(SleepInhibitor, "_activate", activate), patch.object(SleepInhibitor, "_deactivate", deactivate):
        async with SleepInhibitor.hold():
            async with SleepInhibitor.hold():
                assert SleepInhibitor._ref_count == 2

    activate.assert_called_once()
    deactivate.assert_called_once()
    assert SleepInhibitor._ref_count == 0
    assert SleepInhibitor._display_ref_count == 0


@pytest.mark.asyncio()
async def test_noop_outside_local_mode() -> None:
    activate = MagicMock()
    with patch("app.config.deploy_mode.is_local_mode", return_value=False), patch.object(SleepInhibitor, "_activate", activate):
        async with SleepInhibitor.hold(prevent_display_sleep=True):
            pass

    activate.assert_not_called()
    assert SleepInhibitor._ref_count == 0
