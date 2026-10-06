"""locked_use 测试域共享夹具。

[INPUT]
- app.services.locked_use.unattended（POS: 模块级租约/计数状态）

[OUTPUT]
- 每个用例自动复位 watcher 模块级状态的 autouse 夹具

[POS]
watcher 的计数器与租约状态是模块级全局，复位后用例之间互不串扰。
"""

from __future__ import annotations

import pytest

from app.services.locked_use import unattended


@pytest.fixture(autouse=True)
def _reset_watcher_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例重置模块级计数器与租约状态，避免用例间串扰。"""
    monkeypatch.setattr(unattended, "_unlock_failures", 0)
    monkeypatch.setattr(unattended, "_lease_held", False)
    monkeypatch.setattr(unattended, "_release_retry_at", 0.0)
