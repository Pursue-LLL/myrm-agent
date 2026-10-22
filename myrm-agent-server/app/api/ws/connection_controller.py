"""双端同构连接恢复控制器与带抖动指数退避调度器。

汲取 DeepSeek Harness 2026-08-28 `web-connection-recovery-control` 生产级设计：
1. Jittered Exponential Backoff: 500ms ➔ 1s ➔ 2s ➔ 4s ➔ 8s ➔ 10s 封顶；
2. 实际退避延迟取上限的 50%–100% 随机抖动，彻底杜绝并发惊群与重试雪崩；
3. 达到 10s 档最终失败后优雅停止盲目重试，发布 disconnected 等待用户介入；
4. 浏览器网络感知事件联动：offline 立即挂起重试，online 立即重置序号从 500ms 重新发起；
5. CAS 防抖立即重连：点击“立即重连”强制打断当前等待并立即直连。
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

logger = logging.getLogger(__name__)


class ConnectionState(StrEnum):
    """连接生命周期三态枚举。"""

    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    """退避阶梯配置项。"""

    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter_min_ratio: float = 0.5
    jitter_max_ratio: float = 1.0


class JitteredBackoffScheduler:
    """带抖动指数退避调度器。"""

    # 预设的严格阶梯上限序列（秒）
    SCHEDULE_TIERS: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 8.0, 10.0)

    def __init__(self, config: BackoffConfig | None = None) -> None:
        self.config = config or BackoffConfig()
        self._current_attempt: int = 0
        self._is_exhausted: bool = False

    @property
    def current_attempt(self) -> int:
        """当前重试轮次序号（1-indexed）。"""
        return self._current_attempt

    @property
    def is_exhausted(self) -> bool:
        """是否已在最高档（10s）重试失败并耗尽自动重试预算。"""
        return self._is_exhausted

    def reset(self) -> None:
        """重置退避调度器至初始状态。"""
        self._current_attempt = 0
        self._is_exhausted = False

    def next_backoff_delay(self, random_seed: float | None = None) -> float:
        """计算下一轮重试的带抖动延迟时间（秒）。

        如果已在最后一档（10s）重试过且再次失败，则标记耗尽并返回 0.0。
        """
        if self._is_exhausted:
            return 0.0

        tier_index = min(self._current_attempt, len(self.SCHEDULE_TIERS) - 1)
        tier_cap = self.SCHEDULE_TIERS[tier_index]

        # 如果当前尝试已经达到最后一档之后，则判定耗尽
        if self._current_attempt >= len(self.SCHEDULE_TIERS):
            self._is_exhausted = True
            logger.info("Backoff scheduler reached 10s ceiling and exhausted retries.")
            return 0.0

        # 计算 50% - 100% 随机抖动
        rand_ratio = (
            random_seed
            if random_seed is not None
            else random.uniform(self.config.jitter_min_ratio, self.config.jitter_max_ratio)
        )
        # 夹逼到 [0.5, 1.0]
        clamped_ratio = max(
            self.config.jitter_min_ratio,
            min(self.config.jitter_max_ratio, rand_ratio),
        )
        actual_delay = round(tier_cap * clamped_ratio, 3)

        self._current_attempt += 1
        return actual_delay


class ConnectionController:
    """双端连接生命周期与恢复控制器。"""

    def __init__(
        self,
        scheduler: JitteredBackoffScheduler | None = None,
        on_state_change: Callable[[ConnectionState], None] | None = None,
    ) -> None:
        self.scheduler = scheduler or JitteredBackoffScheduler()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._is_online: bool = True
        self._state_subscribers: list[Callable[[ConnectionState], None]] = []
        if on_state_change is not None:
            self._state_subscribers.append(on_state_change)

        self._last_connected_timestamp: float = 0.0
        self._last_reconnect_attempt_timestamp: float = 0.0

    @property
    def state(self) -> ConnectionState:
        """当前连接状态。"""
        return self._state

    @property
    def is_online(self) -> bool:
        """物理网络是否在线（基于浏览器/系统网络事件）。"""
        return self._is_online

    def subscribe(self, listener: Callable[[ConnectionState], None]) -> Callable[[], None]:
        """订阅连接状态变更通知，返回注销函数。"""
        self._state_subscribers.append(listener)

        def unsubscribe() -> None:
            if listener in self._state_subscribers:
                self._state_subscribers.remove(listener)

        return unsubscribe

    def _transition_to(self, new_state: ConnectionState) -> None:
        """状态转移并触发订阅者广播。"""
        if self._state == new_state:
            return
        logger.debug("ConnectionController state: %s -> %s", self._state, new_state)
        self._state = new_state
        for subscriber in list(self._state_subscribers):
            try:
                subscriber(new_state)
            except Exception as exc:
                logger.error("Error in connection state subscriber: %s", exc)

    def mark_connected(self) -> None:
        """连接成功建立，重置重试调度器。"""
        self.scheduler.reset()
        self._last_connected_timestamp = time.monotonic()
        self._transition_to(ConnectionState.CONNECTED)

    def mark_disconnected(self) -> float:
        """连接断开或传输失败，计算下一次重连等待时长。

        如果网络 offline 或重试预算已耗尽，则保持 DISCONNECTED。
        如果仍可重连，进入 CONNECTING 状态并返回等待秒数。
        """
        if not self._is_online:
            self._transition_to(ConnectionState.DISCONNECTED)
            return 0.0

        delay = self.scheduler.next_backoff_delay()
        if self.scheduler.is_exhausted:
            self._transition_to(ConnectionState.DISCONNECTED)
            return 0.0

        self._transition_to(ConnectionState.CONNECTING)
        return delay

    def on_browser_offline(self) -> None:
        """监听到网络离线事件：立即挂起并转为 DISCONNECTED。"""
        self._is_online = False
        logger.info("Browser/network transitioned to OFFLINE. Pausing connection retries.")
        self._transition_to(ConnectionState.DISCONNECTED)

    def on_browser_online(self) -> float:
        """监听到网络恢复在线事件：立即重置退避序号，转为 CONNECTING 并返回首次重连延迟。"""
        self._is_online = True
        logger.info("Browser/network transitioned to ONLINE. Resetting backoff scheduler.")
        self.scheduler.reset()
        self._transition_to(ConnectionState.CONNECTING)
        return self.scheduler.next_backoff_delay()

    def reconnect_now(self) -> bool:
        """用户态显式点击“立即重连”：CAS 防抖、打断等待、重置阶梯并立即发起。"""
        now = time.monotonic()
        # 500ms 严格防抖
        if now - self._last_reconnect_attempt_timestamp < 0.5:
            logger.debug("reconnect_now debounced (last attempt was %.2fs ago)", now - self._last_reconnect_attempt_timestamp)
            return False

        self._last_reconnect_attempt_timestamp = now
        self._is_online = True
        self.scheduler.reset()
        self._transition_to(ConnectionState.CONNECTING)
        logger.info("Immediate reconnect triggered by user action.")
        return True
