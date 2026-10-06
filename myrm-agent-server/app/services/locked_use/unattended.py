"""无人值守帷幕编排 — CU 会话锁屏态的代解锁租约。

[INPUT]
- services.locked_use.curtain_bridge（POS: 状态桥+租约位+静默期/重试上限常量）
- services.locked_use.service.MacScreenUnlocker / release_unlock_lease（POS: 解锁/回锁/探测原语）
- services.agent.gateway.get_agent_gateway（POS: CU 会话活跃判定）

[OUTPUT]
- start_unattended_curtain_watcher（lifespan 启动入口）
- stop_unattended_curtain_watcher（lifespan 关闭入口：停 watcher 并交还仍持有的租约）

[POS]
仅在「CU 会话活跃 + 帷幕拉起（壳存活）+ 屏幕锁定 + 静默期满 + 重试未超限 + 机前无人
（硬件输入空闲）」六条件齐备时获取租约：先置租约位（桌面壳据此在解锁态持续遮蔽屏幕），再代解锁；
解锁后模型经排除截图通道继续作业，物理路过者只见黑幕。租约在 CU 会话
结束时以「校验回锁成功」为前提交还；回锁失败则保留租约（屏幕保持遮蔽，
安全方向）并按冷却间隔重试。屏幕主人撤下帷幕或屏幕被外部重新锁定时租约
直接作废（人在现场，不反锁）；进程重启时接管上一进程遗留的租约位，
经首个 tick 回锁后交还。壳失联（崩溃/被强杀）时帷幕窗口随壳消失、无人再
遮蔽或回锁：持租约则不论会话是否在跑立即校验回锁，未持租约则不再代解锁；
壳优雅退出时由 stop_unattended_curtain_watcher 在 lifespan 关闭最先回锁。
密码错误达上限即暂停编排（现有 Guardian 锁屏拒答行为兜底）；用户亲自解锁
（在场证明）自然重置计数。非桌面端部署（无状态桥文件）watcher 静默空转零成本。
移动端看板经 `GET /remote-access/mobile/sessions` 轮询载体回执帷幕状态
（移动端无 SSE 通道，见 curtain_bridge）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.services.locked_use.curtain_bridge import (
    MAX_UNLOCK_ATTEMPTS,
    CurtainBridgeState,
    clear_pending_auto_unlock,
    mark_pending_auto_unlock,
    read_curtain_state,
)
from app.services.locked_use.service import MacScreenUnlocker, release_unlock_lease

logger = logging.getLogger(__name__)

WATCH_INTERVAL_SECONDS = 5.0
# 回锁失败后的重试冷却：避免持续失败（如无辅助功能权限）时每个 tick 都重放锁屏按键。
RELEASE_RETRY_COOLDOWN_SECONDS = 60.0

_watcher_task: asyncio.Task[None] | None = None
_unlock_failures: int = 0
# 本进程是否持有代解锁租约（租约位已置位且屏幕由我方解锁）。
_lease_held: bool = False
# 下一次允许尝试交还租约的 monotonic 时刻（回锁失败后推迟）。
_release_retry_at: float = 0.0


def start_unattended_curtain_watcher() -> None:
    """启动无人值守帷幕 watcher（幂等；lifespan 启动期调用）。"""
    global _watcher_task
    if _watcher_task is not None and not _watcher_task.done():
        return
    _adopt_orphaned_lease()
    _watcher_task = asyncio.create_task(_watch_loop(), name="unattended-curtain-watcher")
    logger.info("Unattended curtain watcher started")


async def stop_unattended_curtain_watcher() -> None:
    """停止 watcher 并交还仍持有的租约（幂等；lifespan 关闭期最先调用）。

    退出路径上桌面壳随后撤走帷幕窗口：此刻不回锁，屏幕就会以解锁态裸露。
    回锁失败时租约位保持置位，与运行期一致（安全方向）。
    """
    global _watcher_task
    task, _watcher_task = _watcher_task, None
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if _lease_held:
        await _release_lease()


def _adopt_orphaned_lease() -> None:
    """接管上一进程遗留的租约位：帷幕仍在（或壳已失联）则经首个 tick 回锁后交还，否则直接清除。

    遗留的租约位若无人交还，桌面壳会永远不把用户本人的解锁判定为「用户解锁」，
    帷幕滞留到用户手动撤下；壳已失联时屏幕可能仍由上一进程解锁，必须回锁。
    """
    global _lease_held
    state = read_curtain_state()
    if state is None or not state.pending_auto_unlock:
        return
    if state.active or not state.shell_alive:
        _lease_held = True
        logger.warning("[Audit] curtain: adopted an orphaned lease from a previous process")
    else:
        clear_pending_auto_unlock()


def _drop_lease(reason: str) -> None:
    """作废租约并交还标记（无需回锁：屏幕已锁或主人在场）。"""
    global _lease_held
    clear_pending_auto_unlock()
    _lease_held = False
    logger.info("[Audit] curtain: lease dropped (%s)", reason)


async def _release_lease() -> None:
    """交还租约：确认回锁后清除租约位；回锁失败则保留并进入冷却（屏幕保持遮蔽）。"""
    global _lease_held, _release_retry_at
    if await release_unlock_lease():
        _lease_held = False
        logger.info("[Audit] curtain: lease released (screen re-locked)")
        return
    _release_retry_at = time.monotonic() + RELEASE_RETRY_COOLDOWN_SECONDS
    logger.error("[Audit] curtain: re-lock failed; keeping lease so the display stays covered")


async def _release_lease_when_due() -> None:
    """冷却已过才尝试交还租约（回锁持续失败时不每个 tick 都重放锁屏按键）。"""
    if time.monotonic() >= _release_retry_at:
        await _release_lease()


async def _tick_lease_held(state: CurtainBridgeState) -> None:
    """租约持有期：屏幕由我方解锁，帷幕必须持续遮蔽（租约位保持置位）。"""
    if not state.shell_alive:
        # 壳已崩溃/被强杀：帷幕窗口随壳消失，屏幕却仍由我方解锁，没有任何人会再遮蔽或回锁。
        await _release_lease_when_due()
    elif not state.active:
        # 主人已撤下帷幕（托盘/设置页）：无物可护，且人在现场，不得反锁。
        _drop_lease("curtain taken down by the owner")
    elif not await _cu_session_active():
        await _release_lease_when_due()
    elif MacScreenUnlocker.is_locked():
        _drop_lease("screen locked externally")


async def _tick_acquire(state: CurtainBridgeState) -> None:
    """无租约且帷幕拉起：六条件齐备时获取租约并代解锁。"""
    global _unlock_failures, _lease_held
    if not MacScreenUnlocker.is_locked():
        # 用户亲自解锁 = 在场证明，重置重试计数。
        _unlock_failures = 0
        return

    # 超限即暂停：CU 锁屏态由 harness Guardian 拒答兜底，用户亲自解锁后计数自然复位。
    if _unlock_failures >= MAX_UNLOCK_ATTEMPTS or not state.quiet_period_elapsed:
        return
    if not await _cu_session_active():
        return
    # 锁屏态下本人的输入落在登录窗而非帷幕，静默期看不见：此刻代键入会与其串扰。
    # 本 tick 整个跳过——不置租约位、不计失败，输入停下后下个 tick 自然续跑。
    if MacScreenUnlocker.user_present():
        logger.debug("[Audit] curtain: unattended unlock deferred (a user is at the machine)")
        return

    # 租约获取：先置租约位（桌面壳据此维持帷幕），再执行代解锁。
    if not mark_pending_auto_unlock():
        return
    if await MacScreenUnlocker.unlock():
        _unlock_failures = 0
        _lease_held = True
        logger.info("[Audit] curtain: unattended unlock granted (cu session active, quiet period elapsed)")
        return

    # 解锁失败必须立即交还租约，否则帷幕会滞留遮蔽。
    clear_pending_auto_unlock()
    _unlock_failures += 1
    logger.error(
        "[Audit] curtain: unattended unlock attempt failed (%d/%d)",
        _unlock_failures,
        MAX_UNLOCK_ATTEMPTS,
    )


async def _watch_loop() -> None:
    global _lease_held
    while True:
        await asyncio.sleep(WATCH_INTERVAL_SECONDS)
        try:
            state = read_curtain_state()
            if state is None:
                _lease_held = False
            elif _lease_held:
                await _tick_lease_held(state)
            elif state.active:
                await _tick_acquire(state)
        except Exception as error:  # noqa: BLE001 — watcher 必须永不退出
            logger.warning("Unattended curtain watcher tick failed: %s", error)


async def _cu_session_active() -> bool:
    """是否有活跃 CU 会话（解锁只为在跑的任务服务，无任务不解锁）。"""
    from app.services.agent.gateway import get_agent_gateway

    return get_agent_gateway().get_active_desktop_session() is not None
