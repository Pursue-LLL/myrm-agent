"""locked_use 测试域共享夹具。

[INPUT]
- app.services.locked_use.unattended（POS: 模块级租约/计数/在途获取状态）
- app.services.locked_use.curtain_bridge.SHELL_PID_ENV（POS: 壳进程身份环境变量名）

[OUTPUT]
- 每个用例自动复位 watcher 模块级状态、并默认令桌面壳存活、Locked Use 已授权、机前无人的 autouse 夹具
- dead_shell_pid（已退出进程的 PID，模拟壳崩溃）

[POS]
watcher 的计数器、租约与在途获取状态是模块级全局，复位后用例之间互不串扰。
状态桥读侧把「壳存活」折进有效帷幕态：默认以本测试进程充当壳，需要失联场景的用例
改用 dead_shell_pid。授权开关默认开启，需要「未授权」的用例显式关闭。在场探针默认
判定主人已离开，需要「人在机前」的用例经 set_hid_idle 显式声明，避免结果随开发机上的
真实键鼠活动或 CI 平台而变。
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import SHELL_PID_ENV
from tests.support.curtain_watcher import AWAY_IDLE_SECONDS, dead_process_pid, set_hid_idle


@pytest.fixture(autouse=True)
def _reset_watcher_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例重置模块级状态，令桌面壳默认存活、Locked Use 默认已授权、机前默认无人，避免用例间串扰。"""
    monkeypatch.setattr(unattended, "_unlock_failures", 0)
    monkeypatch.setattr(unattended, "_lease_held", False)
    monkeypatch.setattr(unattended, "_release_retry_at", 0.0)
    monkeypatch.setattr(unattended, "_watcher_task", None)
    monkeypatch.setattr(unattended, "_acquire_task", None)
    monkeypatch.setattr(unattended, "_lease_guard", asyncio.Lock())
    monkeypatch.setenv(SHELL_PID_ENV, str(os.getpid()))
    monkeypatch.setenv("MYRM_LOCKED_USE_ENABLED", "true")
    set_hid_idle(monkeypatch, AWAY_IDLE_SECONDS)


@pytest.fixture
def dead_shell_pid() -> int:
    """一个刚退出并已被回收的进程 PID：模拟壳崩溃/被强杀后的失联壳。"""
    return dead_process_pid()
