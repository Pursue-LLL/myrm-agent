"""帷幕状态桥行为单测 — server 侧读写协议与截图排除注入链路。

[INPUT]
- app.services.locked_use.curtain_bridge（POS: 状态桥读写+排除注入）
- app.services.locked_use.unattended._cu_session_active（POS: CU 会话活跃判定）

[OUTPUT]
- 环境开关解析、状态读取降级、pending 写入边界、排除 title 穿透 CuaDriver
  `_fallback` 链注入、状态载荷映射、CU 会话活跃判定

[POS]
与 test_keychain_and_curtain_contract.py（跨语言契约钉死）互补：本文件覆盖
状态桥的行为分支与注入链路，契约文件覆盖 Rust/Python 双实现漂移。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.locked_use import unattended
from app.services.locked_use.curtain_bridge import (
    EXCLUDED_CAPTURE_TITLES,
    apply_excluded_capture_titles,
    curtain_status_payload,
    locked_use_enabled_from_env,
    mark_pending_auto_unlock,
    read_curtain_state,
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
    """桌面端部署：载荷透出 active/autoEngaged/pendingAutoUnlock 三字段。"""
    state_file = _write_state(
        tmp_path,
        monkeypatch,
        json.dumps({**_VALID_STATE, "autoEngaged": True, "pendingAutoUnlock": True}),
    )
    assert state_file.is_file()
    assert curtain_status_payload() == {
        "available": True,
        "active": True,
        "autoEngaged": True,
        "pendingAutoUnlock": True,
    }


def test_publish_state_change_removed() -> None:
    """SSE 广播路径已移除：移动端经 hub 轮询回执（无 SSE 通道）。"""
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
