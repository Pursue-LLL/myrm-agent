"""多端同构轻量流式进度看板中枢 (Multi-Surface Live Progress HUD Hub)。

汲取字节跳动“豆包工作”多端协同核心架构设计：
1. 无论用户打开手机移动端、PC 浏览器 WebUI 还是桌面客户端，均可连接到实时任务总线；
2. 跨端流式同步查看当前执行步骤、即时日志、阶段名称与预估耗时；
3. 新客户端连入时瞬时补发最新进度快照 (Catch-up Snapshot)，拒绝等待下一轮事件；
4. 纯净发布-订阅模型，自动隔离异常订阅者，具备完全解耦的线程/协程安全支持。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StepProgressEvent:
    """跨端流式任务进度事件。"""

    task_id: str
    step_index: int
    total_steps: int
    stage_name: str
    preview_text: str
    elapsed_seconds: float
    estimated_remaining_seconds: float
    timestamp: float = field(default_factory=time.time)
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def percentage(self) -> float:
        """任务完成百分比 (0.0 ~ 100.0)。"""
        if self.total_steps <= 0:
            return 0.0
        return min(100.0, round((self.step_index / self.total_steps) * 100.0, 1))


class LiveProgressHudHub:
    """多端轻量流式进度看板中枢：汇聚、缓存并广播云端长任务的执行轨迹。"""

    def __init__(self) -> None:
        # task_id -> 最新进度快照
        self._latest_snapshots: dict[str, StepProgressEvent] = {}
        # task_id -> 订阅者回调列表
        self._subscribers: dict[str, list[Callable[[StepProgressEvent], None]]] = {}

    def publish_progress(self, event: StepProgressEvent) -> None:
        """广播单步进度事件，更新全局快照并分发至多端订阅者。"""
        task_id = event.task_id
        self._latest_snapshots[task_id] = event

        subscribers = self._subscribers.get(task_id, [])
        for listener in list(subscribers):
            try:
                listener(event)
            except Exception as exc:
                logger.error("Error dispatching HUD progress to subscriber for task %s: %s", task_id, exc)

    def get_latest_progress(self, task_id: str) -> StepProgressEvent | None:
        """查询指定任务当前最新的执行态快照。"""
        return self._latest_snapshots.get(task_id)

    def subscribe(
        self,
        task_id: str,
        listener: Callable[[StepProgressEvent], None],
        replay_latest: bool = True,
    ) -> Callable[[], None]:
        """多端设备（Mobile/Web/Desktop）订阅任务进度。

        参数：
        - task_id: 目标任务 ID
        - listener: 回调函数
        - replay_latest: 是否在订阅成功瞬间立即补发最新快照（默认 True）
        """
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(listener)

        # 瞬时补发最新快照，确保新上线设备立即看到当前进度
        if replay_latest and task_id in self._latest_snapshots:
            try:
                listener(self._latest_snapshots[task_id])
            except Exception as exc:
                logger.error("Error replaying HUD snapshot for task %s: %s", task_id, exc)

        def unsubscribe() -> None:
            if task_id in self._subscribers and listener in self._subscribers[task_id]:
                self._subscribers[task_id].remove(listener)
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]

        return unsubscribe

    def clear_task_progress(self, task_id: str) -> None:
        """任务彻底结项或归档后清理缓存。"""
        self._latest_snapshots.pop(task_id, None)
        self._subscribers.pop(task_id, None)
