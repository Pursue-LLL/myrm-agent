"""锁屏/帷幕跨语言契约守护 — server 与 Tauri 双实现的漂移防线。

[INPUT]
- app.services.locked_use.service.MacScreenUnlocker（POS: server 侧锁屏原语）
- app.services.locked_use.curtain_bridge（POS: 状态桥）
- myrm-agent-desktop/src-tauri/src/{utils/screen_lock.rs, commands/privacy_curtain.rs}
  （POS: Tauri 侧锁屏/帷幕实现，源码字符串契约提取目标）

[OUTPUT]
- Keychain service/account、帷幕窗 title、curtain_state 字段三契约对齐断言
- curtain_state.json 跨进程读写协议 round-trip

[POS]
锁屏原语因跨语言（Rust/Python）与跨进程韧性（任一侧存活即可守屏）
保持双实现；本测试把两侧的跨进程契约（Keychain 条目、窗口 title、
serde 字段）钉死为单一事实源，任何单侧漂移立即变红。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.locked_use.curtain_bridge import (
    EXCLUDED_CAPTURE_TITLES,
    mark_pending_auto_unlock,
    read_curtain_state,
)
from app.services.locked_use.service import MacScreenUnlocker


def _repo_root() -> Path:
    """向上定位 monorepo 根（含桌面端源码树的锚点目录）。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "myrm-agent" / "myrm-agent-desktop").is_dir():
            return parent
    raise AssertionError("monorepo root not found from tests/services/locked_use")


def _tauri_source(relative: str) -> str:
    path = _repo_root() / "myrm-agent" / "myrm-agent-desktop" / "src-tauri" / relative
    return path.read_text(encoding="utf-8")


def test_keychain_service_contract_aligned() -> None:
    """Keychain service 名两侧必须一致（密码写入方=读取方）。"""
    rust = _tauri_source("src/utils/screen_lock.rs")
    match = re.search(r'KEYCHAIN_SERVICE:\s*&str\s*=\s*"([^"]+)"', rust)
    assert match is not None, "Tauri KEYCHAIN_SERVICE constant not found"
    assert match.group(1) == MacScreenUnlocker.KEYCHAIN_SERVICE


def test_keychain_account_contract_aligned() -> None:
    """Keychain account 名两侧必须一致。"""
    rust = _tauri_source("src/utils/screen_lock.rs")
    match = re.search(r'KEYCHAIN_ACCOUNT:\s*&str\s*=\s*"([^"]+)"', rust)
    assert match is not None, "Tauri KEYCHAIN_ACCOUNT constant not found"
    assert match.group(1) == MacScreenUnlocker.KEYCHAIN_ACCOUNT


def test_curtain_window_title_contract_aligned() -> None:
    """CU 截图排除契约：harness 排除 title 必须命中 Tauri 帷幕窗 title。"""
    rust = _tauri_source("src/commands/privacy_curtain.rs")
    match = re.search(r'\.title\("([^"]+)"\)', rust)
    assert match is not None, "Tauri curtain window title not found"
    assert match.group(1) in EXCLUDED_CAPTURE_TITLES


def test_curtain_state_fields_contract_aligned() -> None:
    """curtain_state.json serde 契约：Rust camelCase 字段集与 server 解析字段集一致。"""
    rust = _tauri_source("src/commands/privacy_curtain.rs")
    struct = re.search(r"pub struct CurtainState\s*\{(.*?)\n\}", rust, re.DOTALL)
    assert struct is not None, "Tauri CurtainState struct not found"
    rust_fields = re.findall(r"pub (\w+):", struct.group(1))
    assert rust_fields, "Tauri CurtainState has no public fields"

    # serde(rename_all = "camelCase") 映射：snake_case → lowerCamelCase。
    expected_keys = {
        "".join(part.capitalize() if index else part for index, part in enumerate(field.split("_"))) for field in rust_fields
    }
    # server 侧解析键集合（read_curtain_state 的映射目标）。
    server_keys = {"active", "autoEngaged", "lastPhysicalInputMs", "pendingAutoUnlock"}
    assert expected_keys == server_keys, (
        f"curtain_state.json serde contract drifted: rust={sorted(expected_keys)} server={sorted(server_keys)}"
    )


def test_curtain_state_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """状态桥协议：Rust 写的 camelCase JSON 可被 server 完整解析；server 的
    pending 写入只碰自己拥有的键位，绝不覆写 Tauri 字段。"""
    state_file = tmp_path / "curtain_state.json"
    state_file.write_text(
        json.dumps(
            {
                "active": True,
                "autoEngaged": True,
                "lastPhysicalInputMs": 42,
                "pendingAutoUnlock": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(state_file))

    state = read_curtain_state()
    assert state is not None
    assert state.active is True
    assert state.auto_engaged is True
    assert state.last_physical_input_ms == 42
    assert state.pending_auto_unlock is False

    assert mark_pending_auto_unlock() is True
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["pendingAutoUnlock"] is True
    # server 只写 pending 位：Tauri 拥有的字段必须原样保留。
    assert data["active"] is True
    assert data["autoEngaged"] is True
    assert data["lastPhysicalInputMs"] == 42


def test_curtain_state_missing_file_is_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非桌面端部署（无状态桥文件）静默降级：read → None、mark → False。"""
    monkeypatch.setenv("MYRM_CURTAIN_STATE_FILE", str(tmp_path / "absent.json"))
    assert read_curtain_state() is None
    assert mark_pending_auto_unlock() is False
