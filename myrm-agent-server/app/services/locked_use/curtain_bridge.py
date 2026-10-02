"""帷幕状态桥 — server 与 Tauri 共享的 curtain_state.json 读写。

[INPUT]
- MYRM_CURTAIN_STATE_FILE 环境变量（Tauri python_backend 注入；POS: 桌面端文件桥路径）
- Tauri commands::privacy_curtain（POS: 帷幕窗口状态机的唯一所有者）

[OUTPUT]
- read_curtain_state / mark_pending_auto_unlock / apply_excluded_capture_titles
- CurtainBridgeState / EXCLUDED_CAPTURE_TITLES（POS: CU 截图排除通道的窗口 title 契约）

[POS]
server 无人值守编排与 Tauri 帷幕状态机的唯一共享通道。
读侧（watcher/goal 截图）容忍文件缺失（非桌面端部署零此文件）；
写侧仅 pendingAutoUnlock 标记位（active/autoEngaged/lastPhysicalInputMs
归 Tauri 所有，server 绝不覆写）。与 Tauri 侧无锁并发的最坏交错是
帷幕多保持一个解锁周期（安全方向），无需文件锁。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 与 Tauri privacy_curtain 窗口 title 的跨进程契约（勿单侧改名）。
EXCLUDED_CAPTURE_TITLES: tuple[str, ...] = ("Privacy Curtain",)

# 静默期：帷幕上最近物理输入后 N 秒内不代解锁（防反复触碰驱动的解锁死循环）。
QUIET_PERIOD_SECONDS = 300.0
# 代解锁密码错误重试上限（超限暂停编排；用户亲自解锁自然恢复）。
MAX_UNLOCK_ATTEMPTS = 3


def locked_use_enabled_from_env() -> bool:
    """Tauri SystemConfig 的 locked_use_enabled 经 MYRM_LOCKED_USE_ENABLED 注入。

    非桌面端部署（未注入）恒 False：代解锁仅存在于 Tauri 桌面端授权场景。
    """
    return os.environ.get("MYRM_LOCKED_USE_ENABLED", "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class CurtainBridgeState:
    """curtain_state.json 的 server 侧只读快照。"""

    active: bool
    auto_engaged: bool
    last_physical_input_ms: int
    pending_auto_unlock: bool

    @property
    def quiet_period_elapsed(self) -> bool:
        """最近物理输入距今是否已超过静默期。"""
        elapsed_ms = time.time() * 1000 - self.last_physical_input_ms
        return elapsed_ms / 1000.0 >= QUIET_PERIOD_SECONDS


def curtain_state_path() -> Path | None:
    """状态桥文件路径；非 Tauri 桌面端部署（未注入环境变量）返回 None。"""
    raw = os.environ.get("MYRM_CURTAIN_STATE_FILE", "").strip()
    return Path(raw) if raw else None


def read_curtain_state() -> CurtainBridgeState | None:
    """读帷幕状态；文件缺失/损坏返回 None（调用方按未拉帷幕处理）。"""
    path = curtain_state_path()
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CurtainBridgeState(
            active=bool(data.get("active", False)),
            auto_engaged=bool(data.get("autoEngaged", False)),
            last_physical_input_ms=int(data.get("lastPhysicalInputMs", 0)),
            pending_auto_unlock=bool(data.get("pendingAutoUnlock", False)),
        )
    except (OSError, ValueError, TypeError) as error:
        logger.warning("Curtain state bridge read failed: %s", error)
        return None


def mark_pending_auto_unlock() -> bool:
    """落 pendingAutoUnlock 标记（server 仅有的写权限位）。

    必须在执行解锁前调用：Tauri watcher 观察到解锁态时据此保持帷幕
    （否则按用户本人解锁收起帷幕，屏幕内容裸奔）。幂等无害。
    """
    path = curtain_state_path()
    if path is None or not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["pendingAutoUnlock"] = True
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except (OSError, ValueError) as error:
        logger.warning("Curtain pending flag write failed: %s", error)
        return False


def apply_excluded_capture_titles(session: object) -> bool:
    """向 CU 会话 backend 注入排除窗口 title（穿透 CuaDriver 包装链）。

    幂等恒注入：帷幕未拉起时 harness 找不到匹配窗，自动走原截图路径，
    因此无需按帷幕态做条件开关。返回 False = 平台 backend 无此能力（静默降级）。
    """
    titles = list(EXCLUDED_CAPTURE_TITLES)
    backend = getattr(session, "_backend", None)
    while backend is not None:
        setter = getattr(backend, "set_excluded_capture_window_titles", None)
        if callable(setter):
            setter(titles)
            return True
        backend = getattr(backend, "_fallback", None)
    return False
