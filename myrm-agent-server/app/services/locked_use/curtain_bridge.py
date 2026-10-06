"""帷幕状态桥 — server 与 Tauri 共享的 curtain_state.json 读写。

[INPUT]
- MYRM_CURTAIN_STATE_FILE / MYRM_SHELL_PID 环境变量（Tauri python_backend 注入；POS: 桌面端文件桥路径与壳进程身份）
- Tauri commands::privacy_curtain_state（POS: 帷幕状态桥，curtain_state.json 的 Tauri 侧唯一读写入口）

[OUTPUT]
- read_curtain_state / mark_pending_auto_unlock / clear_pending_auto_unlock
- apply_excluded_capture_titles
- CurtainBridgeState / EXCLUDED_CAPTURE_TITLES（POS: CU 截图排除通道的窗口 title 契约）
- shell_alive / SHELL_PID_ENV（POS: 壳存活判定与跨进程契约名）

[POS]
server 无人值守编排与 Tauri 帷幕状态机的唯一共享通道。
读侧（watcher/goal 截图）容忍文件缺失（非桌面端部署零此文件）；
写侧仅 pendingAutoUnlock 租约位（active/autoEngaged/lastPhysicalInputMs
归 Tauri 所有，server 绝不覆写）。该位是**电平**而非脉冲：服务端持有
代解锁租约期间保持置位（桌面壳据此维持帷幕遮蔽），仅在确认回锁后清除。
双方都以整文件原子替换写入（读者不会读到撕裂文档）；无文件锁，读-改-写之间
的并发写入可能丢失一次更新，仅当 Tauri 恰在同一毫秒因物理输入写盘时发生：
被覆盖的清除只让帷幕多保持（安全方向），被覆盖的置位会使帷幕提前收起。

状态文件里的 active 只是壳最后一次写下的声明：帷幕窗口、输入守卫都活在壳进程里，
壳崩溃/被强杀后文件不会被任何人更新。因此读侧把 ``CurtainBridgeState.active``
定义为**有效**帷幕态（文件 active ∧ 壳存活），代解锁授权、手机端「屏幕已保护」
徽标等所有消费方读到的都是真实遮蔽状态；``shell_alive`` 单独暴露，供 watcher
区分「主人撤下帷幕（人在场，不反锁）」与「壳失联（无人遮蔽，必须回锁）」。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

# 与 Tauri privacy_curtain 窗口 title 的跨进程契约（勿单侧改名）。
EXCLUDED_CAPTURE_TITLES: tuple[str, ...] = ("Privacy Curtain",)

# 与 Tauri python_backend 注入的壳进程 PID 环境变量的跨进程契约（勿单侧改名）。
# release 的 sidecar 是 PyInstaller --onefile：getppid 指向引导进程而非壳，必须显式注入。
SHELL_PID_ENV = "MYRM_SHELL_PID"

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
    """curtain_state.json 的 server 侧只读快照。

    ``active`` 是有效帷幕态（文件 active ∧ 壳存活），不是文件原值。
    """

    active: bool
    auto_engaged: bool
    last_physical_input_ms: int
    pending_auto_unlock: bool
    shell_alive: bool

    @property
    def quiet_period_elapsed(self) -> bool:
        """最近物理输入距今是否已超过静默期。"""
        elapsed_ms = time.time() * 1000 - self.last_physical_input_ms
        return elapsed_ms / 1000.0 >= QUIET_PERIOD_SECONDS


def curtain_state_path() -> Path | None:
    """状态桥文件路径；非 Tauri 桌面端部署（未注入环境变量）返回 None。"""
    raw = os.environ.get("MYRM_CURTAIN_STATE_FILE", "").strip()
    return Path(raw) if raw else None


def shell_alive() -> bool:
    """桌面壳进程是否仍存活（存在、非僵尸、且仍是拉起本 server 的那个壳）。

    壳消失后状态文件里的 active 只是它的遗言。PID 未注入或非法一律按失联处理
    （fail-closed）：状态桥存在而壳身份不明时，宁可不代解锁。

    壳先于它拉起的 server 启动，所以壳的 PID 一旦被无关进程复用，复用者必晚于本进程
    创建——以创建时间先后识别复用，无需记录基线；只在同一时钟粒度内才会把同刻进程当作壳。
    """
    raw = os.environ.get(SHELL_PID_ENV, "").strip()
    if not raw.isdecimal() or int(raw) <= 0:
        return False
    try:
        shell = psutil.Process(int(raw))
        if shell.status() == psutil.STATUS_ZOMBIE:
            return False
        shell_created_at: float = shell.create_time()
        server_created_at: float = psutil.Process().create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return shell_created_at <= server_created_at


def read_curtain_state() -> CurtainBridgeState | None:
    """读帷幕状态；文件缺失/损坏返回 None（调用方按未拉帷幕处理）。"""
    path = curtain_state_path()
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        alive = shell_alive()
        return CurtainBridgeState(
            active=bool(data.get("active", False)) and alive,
            auto_engaged=bool(data.get("autoEngaged", False)),
            last_physical_input_ms=int(data.get("lastPhysicalInputMs", 0)),
            pending_auto_unlock=bool(data.get("pendingAutoUnlock", False)),
            shell_alive=alive,
        )
    except (OSError, ValueError, TypeError) as error:
        logger.warning("Curtain state bridge read failed: %s", error)
        return None


def _write_pending_flag(value: bool) -> bool:
    """Set the server-owned lease bit; False when the bridge file is unusable.

    The file is replaced atomically: the desktop shell polls it every second and a
    truncated document would read as the default (inactive) state.
    """
    path = curtain_state_path()
    if path is None or not path.is_file():
        return False
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["pendingAutoUnlock"] = value
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
        return True
    except (OSError, ValueError) as error:
        logger.warning("Curtain pending flag write failed: %s", error)
        with contextlib.suppress(OSError):
            temp_path.unlink(missing_ok=True)
        return False


def mark_pending_auto_unlock() -> bool:
    """Acquire/hold the unlock lease: the desktop shell keeps the curtain up.

    The flag is a *level*, not a pulse: the shell never consumes it on a tick.
    It stays set for as long as we keep the screen unlocked and is released by
    :func:`clear_pending_auto_unlock` after a verified re-lock. The only other
    writer is the shell's input guard, which clears it together with a lock
    request when someone physically touches the curtain. If this process dies
    mid-lease the flag stays set, so the display remains covered (fail-safe)
    until the next process adopts and releases it.
    """
    return _write_pending_flag(True)


def clear_pending_auto_unlock() -> bool:
    """Release the unlock lease after the screen is verifiably locked again."""
    return _write_pending_flag(False)


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


def curtain_status_payload() -> dict[str, object]:
    """帷幕状态的对外载荷（HTTP 响应与移动端 hub 共用的单一映射）。

    非桌面端部署（无状态桥文件）返回 ``available=False``，消费方据此隐藏帷幕 UI。
    ``active`` 是有效帷幕态：壳已失联时为 False，手机端不会再显示「屏幕已保护」。
    """
    state = read_curtain_state()
    if state is None:
        return {"available": False, "active": False}
    return {
        "available": True,
        "active": state.active,
        "autoEngaged": state.auto_engaged,
        "pendingAutoUnlock": state.pending_auto_unlock,
    }
