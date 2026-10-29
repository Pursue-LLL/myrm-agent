"""WebSocket 心跳探测与死线截断控制器。

[INPUT]
- 标准库 asyncio / time / logging (POS: 心跳轮询协程、单调时钟与日志)
- 调用方注入的 ping_sender / socket_closer (POS: 发送 Ping 控制帧、以指定关闭码关闭 socket)

[OUTPUT]
- HeartbeatConfig, HeartbeatStats: 心跳间隔与死线配置（默认 2s 活跃、15s 空闲、Pong 死线 2s）、Ping/Pong 与 RTT 遥测
- AdaptiveHeartbeatController: 每个周期检查上一轮 Pong 是否超时，超时或 Ping 发送失败即关闭 socket；
  按调用方标记的工作负载状态在活跃与空闲间隔之间切换；提供启动 / 停止后台轮询协程

[POS]
僵尸连接在一个心跳周期内被识别并关闭，空闲会话降频探测；是否有进行中的工作由调用方标记，本模块不自行判断。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HeartbeatConfig:
    """心跳控制器配置项。"""

    active_interval_seconds: float = 2.0
    idle_interval_seconds: float = 15.0
    pong_deadline_seconds: float = 2.0
    max_missed_pongs: int = 1


@dataclass(slots=True)
class HeartbeatStats:
    """心跳运行时遥测与监控统计。"""

    total_pings_sent: int = 0
    total_pongs_received: int = 0
    last_ping_timestamp: float = 0.0
    last_pong_timestamp: float = 0.0
    last_rtt_ms: float = 0.0
    dead_links_terminated: int = 0
    current_interval_seconds: float = 2.0


class AdaptiveHeartbeatController:
    """自适应 WebSocket 心跳探针与死线截断控制器。"""

    def __init__(
        self,
        config: HeartbeatConfig | None = None,
        ping_sender: Callable[[], Awaitable[None]] | None = None,
        socket_closer: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config or HeartbeatConfig()
        self._ping_sender = ping_sender
        self._socket_closer = socket_closer
        self.stats = HeartbeatStats(current_interval_seconds=self.config.active_interval_seconds)

        self._is_active_workload: bool = True
        self._waiting_for_pong: bool = False
        self._missed_pong_count: int = 0
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None

    @property
    def is_waiting_for_pong(self) -> bool:
        """当前是否正在等待客户端回复 Pong。"""
        return self._waiting_for_pong

    @property
    def missed_pong_count(self) -> int:
        """连续未收到 Pong 的计数。"""
        return self._missed_pong_count

    def mark_workload_state(self, is_active: bool) -> None:
        """标记会话工作负载状态（活跃打字/长任务 vs 完全空闲）。"""
        self._is_active_workload = is_active
        new_interval = self.config.active_interval_seconds if is_active else self.config.idle_interval_seconds
        self.stats.current_interval_seconds = new_interval
        logger.debug("Heartbeat interval adapted to %.1fs (active=%s)", new_interval, is_active)

    def record_pong_received(self, receive_timestamp: float | None = None) -> float:
        """收到客户端 Pong 响应，结算 RTT 并解除死线等待。"""
        now = receive_timestamp or time.monotonic()
        rtt_ms = 0.0
        if self._waiting_for_pong and self.stats.last_ping_timestamp > 0:
            rtt_ms = max(0.0, (now - self.stats.last_ping_timestamp) * 1000.0)
            self.stats.last_rtt_ms = rtt_ms

        self._waiting_for_pong = False
        self._missed_pong_count = 0
        self.stats.total_pongs_received += 1
        self.stats.last_pong_timestamp = now
        return rtt_ms

    async def execute_heartbeat_tick(self, now: float | None = None) -> bool:
        """执行单次心跳检测周期。

        返回值：
        - True：连接健康，继续维持；
        - False：死线超时，已触发快速摘除终止。
        """
        current_time = now or time.monotonic()

        # 1. 检查上一轮是否等待超时
        if self._waiting_for_pong:
            self._missed_pong_count += 1
            elapsed = current_time - self.stats.last_ping_timestamp
            if self._missed_pong_count >= self.config.max_missed_pongs or elapsed >= self.config.pong_deadline_seconds:
                logger.warning(
                    "Heartbeat deadline breached! Missed pongs=%d, elapsed=%.2fs. Terminating socket.",
                    self._missed_pong_count,
                    elapsed,
                )
                self.stats.dead_links_terminated += 1
                if self._socket_closer is not None:
                    await self._socket_closer(1008, "Heartbeat deadline exceeded: dead link terminated")
                return False

        # 2. 发送新一轮 Ping
        self.stats.last_ping_timestamp = current_time
        self.stats.total_pings_sent += 1
        self._waiting_for_pong = True

        if self._ping_sender is not None:
            try:
                await self._ping_sender()
            except Exception as exc:
                logger.error("Failed to send ping control frame: %s. Terminating socket.", exc)
                self.stats.dead_links_terminated += 1
                if self._socket_closer is not None:
                    await self._socket_closer(1011, f"Failed to send ping: {exc}")
                return False

        return True

    async def start(self) -> None:
        """启动后台自适应心跳轮询协程。"""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop(), name="ws-heartbeat-loop")

    async def stop(self) -> None:
        """优雅停止后台心跳协程。"""
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    async def _run_loop(self) -> None:
        """后台心跳轮询主循环。"""
        while not self._stop_event.is_set():
            is_healthy = await self.execute_heartbeat_tick()
            if not is_healthy:
                break

            interval = self.stats.current_interval_seconds
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break  # 收到停止事件
            except asyncio.TimeoutError:
                continue
