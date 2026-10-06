"""帷幕状态桥行为单测 — server 侧读写协议与截图排除注入链路。

[INPUT]
- app.services.locked_use.curtain_bridge（POS: 状态桥读写+排除注入）
- app.services.locked_use.unattended._cu_session_active（POS: CU 会话活跃判定）

[OUTPUT]
- 环境开关解析、状态读取降级、pending 写入边界与原子替换、排除 title 穿透 CuaDriver
  `_fallback` 链注入、状态载荷映射、CU 会话活跃判定
- 壳存活判定（缺失/非法 PID fail-closed、僵尸/退出/无权限/PID 被晚于本进程的进程复用按失联）与其折入有效帷幕态
  （壳失联时 active=False 而租约位原样保留，载荷如实）

[POS]
与 test_keychain_and_curtain_contract.py（跨语言契约钉死）互补：本文件覆盖
状态桥的行为分支与注入链路，契约文件覆盖 Rust/Python 双实现漂移。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    EXCLUDED_CAPTURE_TITLES,
    SHELL_PID_ENV,
    apply_excluded_capture_titles,
    clear_pending_auto_unlock,
    curtain_status_payload,
    locked_use_enabled_from_env,
    mark_pending_auto_unlock,
    read_curtain_state,
    shell_alive,
)

_VALID_STATE = {
    "active": True,
    "autoEngaged": False,
    "lastPhysicalInputMs": 0,
    "pendingAutoUnlock": False,
}


def _write_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str) -> Path:
    state_file = tmp_path / "curtain_state.json"
    state_file.write_text(payload, encoding="utf-8")
    monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(state_file))
    return state_file


class _FakeBackend:
    """模拟 platform backend：可选排除 title setter + 任意深度 fallback 链。"""

    def __init__(self, *, has_setter: bool = True, fallback: object | None = None) -> None:
        self._fallback = fallback
        self.setter: MagicMock = MagicMock()
        if has_setter:
            self.set_excluded_capture_window_titles = self.setter


def _session(backend: object | None) -> object:
    session = MagicMock()
    session._backend = backend
    return session


def test_locked_use_enabled_env_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tauri 注入的授权开关：1/true/yes（大小写与空白容忍）为真。"""
    for raw in ("1", "true", "TRUE", "Yes", " true "):
        monkeypatch.setenv("MYRM_LOCKED_USE_ENABLED", raw)
        assert locked_use_enabled_from_env() is True


def test_locked_use_enabled_env_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入或非真值恒 False（代解锁仅存在于 Tauri 授权场景）。"""
    for raw in ("", "0", "false", "no", "on"):
        monkeypatch.setenv("MYRM_LOCKED_USE_ENABLED", raw)
        assert locked_use_enabled_from_env() is False
    monkeypatch.delenv("MYRM_LOCKED_USE_ENABLED", raising=False)
    assert locked_use_enabled_from_env() is False


def test_read_state_corrupt_json_degrades_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """状态文件损坏：记录警告并降级 None（调用方按未拉帷幕处理）。"""
    _write_state(tmp_path, monkeypatch, "{not-json")
    with caplog.at_level("WARNING"):
        assert read_curtain_state() is None
    assert "Curtain state bridge read failed" in caplog.text


def test_read_state_uncoercible_field_degrades_to_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """字段类型不可强转（lastPhysicalInputMs 非数值）：降级 None 而非崩溃。"""
    _write_state(tmp_path, monkeypatch, json.dumps({**_VALID_STATE, "lastPhysicalInputMs": "abc"}))
    assert read_curtain_state() is None


def test_read_state_no_env_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入环境变量（非桌面端部署）：返回 None 零成本空转。"""
    monkeypatch.delenv("MYRM_CURTAIN_STATE_FILE", raising=False)
    assert read_curtain_state() is None


def test_mark_pending_rejects_non_dict_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """文件内容是 JSON 数组等非对象：拒绝写入（False）而非破坏文件。"""
    state_file = _write_state(tmp_path, monkeypatch, "[1, 2, 3]")
    assert mark_pending_auto_unlock() is False
    assert state_file.read_text(encoding="utf-8") == "[1, 2, 3]"


def test_mark_pending_missing_file_returns_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """文件缺失（尚未拉起帷幕）：返回 False，调用方据此放弃解锁。"""
    monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(tmp_path / "absent.json"))
    assert mark_pending_auto_unlock() is False


def test_mark_pending_write_failure_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """写盘失败（权限/磁盘）：记录警告返回 False，绝不抛出中断 watcher。"""
    state_file = _write_state(tmp_path, monkeypatch, json.dumps(_VALID_STATE))
    monkeypatch.setattr(Path, "write_text", MagicMock(side_effect=OSError("read-only")))
    with caplog.at_level("WARNING"):
        assert mark_pending_auto_unlock() is False
    assert "Curtain pending flag write failed" in caplog.text
    assert state_file.read_text(encoding="utf-8") == json.dumps(_VALID_STATE)


def test_mark_pending_replaces_the_file_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """写入走「临时文件 + 原子替换」：成功后不留临时文件，内容为新值。"""
    state_file = _write_state(tmp_path, monkeypatch, json.dumps(_VALID_STATE))
    assert mark_pending_auto_unlock() is True
    assert list(tmp_path.glob("*.tmp")) == []
    assert json.loads(state_file.read_text(encoding="utf-8"))["pendingAutoUnlock"] is True


def test_mark_pending_failed_replace_keeps_original_and_removes_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """替换失败：原文件原样保留（桌面壳读到的仍是完整旧文档），临时文件被清理。"""
    state_file = _write_state(tmp_path, monkeypatch, json.dumps(_VALID_STATE))
    with patch("app.services.locked_use.curtain_bridge.os.replace", side_effect=OSError("busy")):
        assert mark_pending_auto_unlock() is False
    assert state_file.read_text(encoding="utf-8") == json.dumps(_VALID_STATE)
    assert list(tmp_path.glob("*.tmp")) == []


def test_reader_never_sees_a_torn_state_file_while_the_lease_bit_flips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """桌面壳每秒轮询该文件：读者在租约位翻转期间绝不能读到被截断的文档（会被当成默认态）。"""
    state_file = _write_state(tmp_path, monkeypatch, json.dumps(_VALID_STATE))
    stop = threading.Event()
    torn: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            content = state_file.read_text(encoding="utf-8")
            try:
                json.loads(content)
            except ValueError:
                torn.append(content)

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for round_index in range(1500):
            flip = mark_pending_auto_unlock if round_index % 2 == 0 else clear_pending_auto_unlock
            assert flip() is True
    finally:
        stop.set()
        thread.join()
    assert torn == []


def test_apply_titles_injects_into_direct_backend() -> None:
    """原生 backend 直接暴露 setter：一次注入命中，返回 True。"""
    backend = _FakeBackend()
    assert apply_excluded_capture_titles(_session(backend)) is True
    backend.setter.assert_called_once_with(list(EXCLUDED_CAPTURE_TITLES))


def test_apply_titles_pierces_cua_driver_fallback_chain() -> None:
    """CuaDriver 无 setter 时穿透 `_fallback` 委托到原生 backend（注入真实生效）。"""
    native = _FakeBackend()
    driver = _FakeBackend(has_setter=False, fallback=native)
    assert apply_excluded_capture_titles(_session(driver)) is True
    native.setter.assert_called_once_with(list(EXCLUDED_CAPTURE_TITLES))


def test_apply_titles_without_capability_returns_false() -> None:
    """链上无 setter（Windows/Linux）：返回 False 静默降级，不抛异常。"""
    deepest = _FakeBackend(has_setter=False)
    middle = _FakeBackend(has_setter=False, fallback=deepest)
    assert apply_excluded_capture_titles(_session(middle)) is False


def test_apply_titles_without_backend_returns_false() -> None:
    """会话无 backend 属性：返回 False（能力检测失败不应致命）。"""
    assert apply_excluded_capture_titles(_session(None)) is False


def test_curtain_status_payload_unavailable_without_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非桌面端部署（无状态桥）：载荷 available=False，消费方据此隐藏 UI。"""
    monkeypatch.delenv("MYRM_CURTAIN_STATE_FILE", raising=False)
    assert curtain_status_payload() == {"available": False, "active": False}


def test_curtain_status_payload_maps_active_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """桌面端部署：载荷只透出消费方需要的 available/active，状态机内部位不外泄。"""
    state_file = _write_state(
        tmp_path,
        monkeypatch,
        json.dumps({**_VALID_STATE, "autoEngaged": True, "pendingAutoUnlock": True}),
    )
    assert state_file.is_file()
    assert curtain_status_payload() == {"available": True, "active": True}


def test_shell_alive_true_for_a_running_process() -> None:
    """conftest 以测试进程充当壳：存在且非僵尸即存活。"""
    assert shell_alive() is True


@pytest.mark.parametrize("raw", [None, "", "  ", "abc", "-5", "0", "1.5", "12x"])
def test_shell_alive_fails_closed_on_missing_or_invalid_pid(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> None:
    """状态桥存在而壳身份不明（未注入/非法/非正）：按失联处理，宁可不代解锁。"""
    if raw is None:
        monkeypatch.delenv(SHELL_PID_ENV, raising=False)
    else:
        monkeypatch.setenv(SHELL_PID_ENV, raw)
    assert shell_alive() is False


def test_shell_alive_false_for_an_exited_process(monkeypatch: pytest.MonkeyPatch, dead_shell_pid: int) -> None:
    """壳崩溃/被强杀后其 PID 不再存在。"""
    monkeypatch.setenv(SHELL_PID_ENV, str(dead_shell_pid))
    assert shell_alive() is False


def test_shell_alive_treats_a_zombie_as_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """僵尸进程仍占着 PID 但已不运行：不算存活。"""
    zombie = MagicMock()
    zombie.status.return_value = psutil.STATUS_ZOMBIE
    monkeypatch.setattr(psutil, "Process", lambda _pid: zombie)
    assert shell_alive() is False


def test_shell_alive_false_when_the_pid_was_reused_by_a_newer_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """壳的 PID 被无关进程复用：它必晚于本进程创建，不能冒充壳而让已消失的帷幕继续授权代解锁。"""
    reuser = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        monkeypatch.setenv(SHELL_PID_ENV, str(reuser.pid))
        assert shell_alive() is False
    finally:
        reuser.kill()
        reuser.wait()


@pytest.mark.parametrize(
    ("shell_created_at", "expected"),
    [(100.0, True), (200.0, True), (200.001, False)],
    ids=["shell-started-first", "same-clock-tick", "started-after-the-server"],
)
def test_shell_alive_orders_the_shell_before_the_server(
    monkeypatch: pytest.MonkeyPatch, shell_created_at: float, expected: bool
) -> None:
    """真壳不晚于它拉起的 server；同一时钟粒度内的同刻进程仍按真壳处理（不误判存活的壳为失联）。"""
    shell = MagicMock()
    shell.status.return_value = psutil.STATUS_SLEEPING
    shell.create_time.return_value = shell_created_at
    server = MagicMock()
    server.create_time.return_value = 200.0
    monkeypatch.setattr(psutil, "Process", lambda pid=None: server if pid is None else shell)

    assert shell_alive() is expected


@pytest.mark.parametrize("error", [psutil.NoSuchProcess(1), psutil.AccessDenied(1)])
def test_shell_alive_false_when_the_process_cannot_be_inspected(monkeypatch: pytest.MonkeyPatch, error: psutil.Error) -> None:
    """检查途中进程消失或无权限读取：按失联处理，绝不抛出打断 watcher。"""
    monkeypatch.setattr(psutil, "Process", MagicMock(side_effect=error))
    assert shell_alive() is False


def test_read_state_active_requires_a_living_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dead_shell_pid: int) -> None:
    """文件里的 active 只是壳的遗言：壳失联后有效帷幕态为 False，其余字段原样透传。"""
    _write_state(tmp_path, monkeypatch, json.dumps({**_VALID_STATE, "autoEngaged": True, "pendingAutoUnlock": True}))

    live = read_curtain_state()
    assert live is not None
    assert (live.active, live.shell_alive) == (True, True)

    monkeypatch.setenv(SHELL_PID_ENV, str(dead_shell_pid))
    gone = read_curtain_state()
    assert gone is not None
    assert (gone.active, gone.shell_alive) == (False, False)
    # 租约位是 server 自己的账：壳失联不能让它凭空消失，watcher 要凭它回锁。
    assert gone.auto_engaged is True
    assert gone.pending_auto_unlock is True


def test_curtain_status_payload_reports_inactive_when_the_shell_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dead_shell_pid: int
) -> None:
    """手机端「屏幕已保护」徽标读这个载荷：壳失联后必须如实显示未保护。"""
    _write_state(tmp_path, monkeypatch, json.dumps(_VALID_STATE))
    monkeypatch.setenv(SHELL_PID_ENV, str(dead_shell_pid))

    assert curtain_status_payload() == {"available": True, "active": False}


def test_unattended_has_no_sse_broadcast_entry() -> None:
    """移动端无 SSE 通道：帷幕状态只经 hub 轮询载体回执，编排模块不持有广播入口。"""
    assert not hasattr(unattended, "_publish_state_change")


def test_cu_session_active_reads_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """CU 会话活跃判定委托 gateway；无活跃会话返回 False。"""
    import asyncio

    gateway = MagicMock()
    gateway.get_active_desktop_session.return_value = None
    monkeypatch.setattr("app.services.agent.gateway.get_agent_gateway", lambda: gateway)
    assert asyncio.run(unattended._cu_session_active()) is False

    gateway.get_active_desktop_session.return_value = object()
    assert asyncio.run(unattended._cu_session_active()) is True
