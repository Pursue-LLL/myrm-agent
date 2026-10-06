"""无人值守帷幕编排 — CU 工具撞上锁屏时的按需代解锁租约。

[INPUT]
- services.locked_use.curtain_bridge（POS: 状态桥+租约位+Locked Use 授权开关+静默期/重试上限常量+截图排除注入）
- services.locked_use.service.MacScreenUnlocker / release_unlock_lease（POS: 解锁/回锁/探测原语）
- services.agent.gateway.get_agent_gateway（POS: CU 会话活跃判定）
- harness ComputerSession.set_screen_unlock_callback（POS: Guardian 的锁屏按需解锁注入点）

[OUTPUT]
- attach_desktop_session（CU 会话与帷幕的唯一接线：截图排除通道 + 锁屏按需解锁）
- unlock_screen_on_demand（Guardian 的锁屏回调）
- start_unattended_curtain_watcher（lifespan 启动入口）
- stop_unattended_curtain_watcher（lifespan 关闭入口：停 watcher 并交还仍持有的租约）

[POS]
租约由需求驱动：CU 工具真正撞上锁屏时 harness Guardian 才回调 unlock_screen_on_demand，
没有 CU 工具调用就没有解锁（纯文本任务不触碰屏幕）。「Locked Use 已授权 + 帷幕有效（壳存活）
+ 静默期满 + 重试未超限 + 机前无人（硬件输入空闲）」五条件齐备时，先置租约位（桌面壳据此在
解锁态持续遮蔽屏幕）再代解锁；Guardian 重探测放行后模型经排除截图通道继续作业，物理路过者
只见黑幕。获取单飞且有界等待：并发工具调用共享同一次键入，超时只放弃本次等待。获取只在
watcher 运行时受理——租约的持有期监护与交还都由它承担，没有它兜底就不能解锁。
watcher（5s tick）监护租约：CU 会话结束时以「校验回锁成功」为前提交还；回锁失败则保留租约
（屏幕保持遮蔽，安全方向）并按冷却间隔重试。屏幕主人撤下帷幕或屏幕被外部重新锁定时租约
直接作废（人在现场，不反锁）；进程重启时接管上一进程遗留的租约位，经首个 tick 回锁后交还。
壳失联（崩溃/被强杀）时帷幕窗口随壳消失、无人再遮蔽或回锁：持租约则不论会话是否在跑立即
校验回锁，未持租约则不再代解锁；壳优雅退出时由 stop_unattended_curtain_watcher 在 lifespan
关闭最先回锁（在途获取先走完再交还）。密码错误达上限即暂停代解锁（Guardian 照常拒答兜底）；
用户亲自解锁（在场证明）由 watcher 重置计数。非桌面端部署（无状态桥文件）watcher 静默空转
零成本。移动端看板经 `GET /remote-access/mobile/sessions` 轮询载体回执帷幕状态
（移动端无 SSE 通道，见 curtain_bridge）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from app.services.locked_use.curtain_bridge import (
    MAX_UNLOCK_ATTEMPTS,
    CurtainBridgeState,
    apply_excluded_capture_titles,
    clear_pending_auto_unlock,
    locked_use_enabled_from_env,
    mark_pending_auto_unlock,
    read_curtain_state,
)
from app.services.locked_use.service import MacScreenUnlocker, release_unlock_lease

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.computer_use import ComputerSession

logger = logging.getLogger(__name__)

WATCH_INTERVAL_SECONDS = 5.0
# 回锁失败后的重试冷却：避免持续失败（如无辅助功能权限）时每个 tick 都重放锁屏按键。
RELEASE_RETRY_COOLDOWN_SECONDS = 60.0
# 按需解锁的有界等待：远超唤醒 + 键入 + 校验的正常耗时（数秒），超时只放弃本次等待。
ON_DEMAND_WAIT_SECONDS = 20.0

_watcher_task: asyncio.Task[None] | None = None
# 在途的租约获取（单飞）：并发的 CU 工具调用共享它。
_acquire_task: asyncio.Task[None] | None = None
# 串行化租约的获取与交还：交还中途发起的获取必须等回锁收尾，否则交还尾部会清掉新租约位。
_lease_guard = asyncio.Lock()
_unlock_failures: int = 0
# 本进程是否持有代解锁租约（租约位已置位且屏幕由我方解锁）。
_lease_held: bool = False
# 下一次允许尝试交还租约的 monotonic 时刻（回锁失败后推迟）。
_release_retry_at: float = 0.0


def attach_desktop_session(session: ComputerSession) -> bool:
    """CU 会话与帷幕的唯一接线点：锁屏按需解锁 + 截图排除通道。

    返回截图排除通道是否可用（False = 平台 backend 无此能力，静默降级）。
    """
    session.set_screen_unlock_callback(unlock_screen_on_demand)
    return apply_excluded_capture_titles(session)


async def unlock_screen_on_demand() -> None:
    """Guardian 的锁屏回调：CU 工具撞上锁屏时按需代解锁；是否真的解开由 Guardian 重探测裁决。

    单飞：并发调用共享同一次获取，不会有第二轮密码键入落进已解锁的桌面。有界等待：超时或
    调用方被取消只放弃等待，获取任务继续跑完，租约状态始终自洽（持有期监护交给 watcher）。
    """
    global _acquire_task
    if _watcher_task is None or _watcher_task.done():
        return
    if _acquire_task is None or _acquire_task.done():
        _acquire_task = asyncio.create_task(_acquire_lease(), name="unattended-lease-acquire")
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(asyncio.shield(_acquire_task), ON_DEMAND_WAIT_SECONDS)


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

    退出路径上桌面壳随后撤走帷幕窗口：此刻不回锁，屏幕就会以解锁态裸露。在途的租约获取
    先走完再交还：已派出的键入取消不掉，只会让屏幕在无人看管时解锁。
    回锁失败时租约位保持置位，与运行期一致（安全方向）。
    """
    global _watcher_task, _acquire_task
    task, _watcher_task = _watcher_task, None
    acquire, _acquire_task = _acquire_task, None
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if acquire is not None:
        await asyncio.wait({acquire}, timeout=ON_DEMAND_WAIT_SECONDS)
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
    async with _lease_guard:
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


async def _acquire_lease() -> None:
    """五条件齐备时代解锁并持有租约；任一不满足即放弃，由 Guardian 的重探测维持锁屏拒答。"""
    global _unlock_failures, _lease_held
    async with _lease_guard:
        state = read_curtain_state()
        if state is None or not state.active or not locked_use_enabled_from_env():
            return
        if _lease_held:
            # 持租约期间屏幕又被锁上（自动锁屏，或主人离场前手动锁定）：旧租约已无对象。
            _drop_lease("screen locked externally")
        # 超限即暂停：CU 锁屏态由 harness Guardian 拒答兜底，用户亲自解锁后计数自然复位。
        if _unlock_failures >= MAX_UNLOCK_ATTEMPTS or not state.quiet_period_elapsed:
            return
        # 锁屏态下本人的输入落在登录窗而非帷幕，静默期看不见：此刻代键入会与其串扰。
        # 整次获取放弃——不置租约位、不计失败，输入停下后的下一次工具调用自然续跑。
        if MacScreenUnlocker.user_present():
            logger.debug("[Audit] curtain: unattended unlock deferred (a user is at the machine)")
            return

        # 租约获取：先置租约位（桌面壳据此维持帷幕），再执行代解锁。
        if not mark_pending_auto_unlock():
            return
        try:
            unlocked = await MacScreenUnlocker.unlock()
        except Exception:
            # 键入尚未发生的失败：必须立即交还租约位，否则帷幕会滞留遮蔽。
            # 取消（BaseException）不在此列：已派出的键入可能已解锁屏幕，租约位保持置位由下一进程接管。
            clear_pending_auto_unlock()
            raise
        if unlocked:
            _unlock_failures = 0
            _lease_held = True
            logger.info("[Audit] curtain: unattended unlock granted (screen locked under an active curtain)")
            return

        # 解锁失败必须立即交还租约，否则帷幕会滞留遮蔽。
        clear_pending_auto_unlock()
        _unlock_failures += 1
        logger.error(
            "[Audit] curtain: unattended unlock attempt failed (%d/%d)",
            _unlock_failures,
            MAX_UNLOCK_ATTEMPTS,
        )


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


async def _watch_loop() -> None:
    global _lease_held, _unlock_failures
    while True:
        await asyncio.sleep(WATCH_INTERVAL_SECONDS)
        try:
            state = read_curtain_state()
            if state is None:
                _lease_held = False
            elif _lease_held:
                await _tick_lease_held(state)
            elif not MacScreenUnlocker.is_locked():
                # 用户亲自解锁 = 在场证明，重置重试计数。
                _unlock_failures = 0
        except Exception as error:  # noqa: BLE001 — watcher 必须永不退出
            logger.warning("Unattended curtain watcher tick failed: %s", error)


async def _cu_session_active() -> bool:
    """是否有活跃 CU 会话（持租约只为在跑的任务服务，无任务即交还）。"""
    from app.services.agent.gateway import get_agent_gateway

    return get_agent_gateway().get_active_desktop_session() is not None
