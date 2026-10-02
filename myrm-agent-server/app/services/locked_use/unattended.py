"""无人值守帷幕编排 — CU 会话锁屏态的代解锁 watcher。

[INPUT]
- services.locked_use.curtain_bridge（POS: 状态桥+静默期/重试上限常量）
- services.locked_use.service.MacScreenUnlocker（POS: 解锁执行原语）
- services.agent.gateway.get_agent_gateway（POS: CU 会话活跃判定）

[OUTPUT]
- start_unattended_curtain_watcher（lifespan 启动入口）

[POS]
仅在「CU 会话活跃 + 帷幕拉起 + 屏幕锁定 + 静默期满 + 重试未超限」五条件
齐备时代解锁：pending 标记先落盘（Tauri watcher 据此在解锁态保持帷幕），
解锁后模型经排除截图通道继续作业，物理路过者只见黑幕。密码错误达上限
即暂停编排（现有 Guardian 锁屏拒答行为兜底）；用户亲自解锁（在场证明）
自然重置计数。非桌面端部署（无状态桥文件）watcher 静默空转零成本。
"""

from __future__ import annotations

import asyncio
import logging

from app.services.locked_use.curtain_bridge import (
    MAX_UNLOCK_ATTEMPTS,
    CurtainBridgeState,
    mark_pending_auto_unlock,
    read_curtain_state,
)
from app.services.locked_use.service import MacScreenUnlocker

logger = logging.getLogger(__name__)

WATCH_INTERVAL_SECONDS = 5.0

_watcher_task: asyncio.Task[None] | None = None
_unlock_failures: int = 0
_last_published_active: bool | None = None


def _publish_state_change(state: CurtainBridgeState) -> None:
    """帷幕状态边沿广播（通知 SSE 流含移动端订阅者，天然回执）。"""
    from app.services.event.app_event_bus import (
        AppEvent,
        AppEventType,
        get_event_bus,
    )

    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.PRIVACY_CURTAIN_UPDATED,
            data={
                "active": state.active,
                "autoEngaged": state.auto_engaged,
                "pendingAutoUnlock": state.pending_auto_unlock,
            },
        )
    )


def start_unattended_curtain_watcher() -> None:
    """启动无人值守帷幕 watcher（幂等；lifespan 启动期调用）。"""
    global _watcher_task
    if _watcher_task is not None and not _watcher_task.done():
        return
    _watcher_task = asyncio.create_task(_watch_loop(), name="unattended-curtain-watcher")
    logger.info("Unattended curtain watcher started")


async def _watch_loop() -> None:
    global _unlock_failures, _last_published_active
    while True:
        await asyncio.sleep(WATCH_INTERVAL_SECONDS)
        try:
            state = read_curtain_state()
            if state is None:
                continue

            # 状态边沿：活跃切换（含拉起/收起）时广播一次（移动端回执）。
            if state.active != _last_published_active:
                _last_published_active = state.active
                _publish_state_change(state)

            if not state.active:
                continue

            if not MacScreenUnlocker.is_locked():
                # 用户亲自解锁 = 在场证明，重置重试计数。
                _unlock_failures = 0
                continue

            if _unlock_failures >= MAX_UNLOCK_ATTEMPTS:
                # 超限即暂停：CU 锁屏态由 harness Guardian 拒答兜底，
                # 用户亲自解锁后计数自然复位。
                continue
            if not state.quiet_period_elapsed:
                continue
            if not await _cu_session_active():
                continue

            # 代解锁协议：pending 先落盘（Tauri 消费后保持帷幕），再执行解锁。
            if not mark_pending_auto_unlock():
                continue
            if await MacScreenUnlocker.unlock():
                _unlock_failures = 0
                logger.info(
                    "[Audit] curtain: unattended unlock granted "
                    "(cu session active, quiet period elapsed)"
                )
            else:
                _unlock_failures += 1
                logger.error(
                    "[Audit] curtain: unattended unlock attempt failed (%d/%d)",
                    _unlock_failures,
                    MAX_UNLOCK_ATTEMPTS,
                )
        except Exception as error:  # noqa: BLE001 — watcher 必须永不退出
            logger.warning("Unattended curtain watcher tick failed: %s", error)


async def _cu_session_active() -> bool:
    """是否有活跃 CU 会话（解锁只为在跑的任务服务，无任务不解锁）。"""
    from app.services.agent.gateway import get_agent_gateway

    return get_agent_gateway().get_active_desktop_session() is not None
