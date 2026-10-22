"""全场景相对延迟与多频段可视化时间调度引擎模块。

聚合相对时间解析器、多频段计算引擎与自愈归档账本，
提供一次性任务秒级注册、到期精确执行、自愈自动归档与智能体活跃态解绑的闭环调度服务。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from app.core.cron.lifecycle_archive_ledger import (
    LifecycleArchiveLedger,
    TaskRecord,
)
from app.core.cron.multi_frequency_descriptor import (
    FrequencyKind,
    MultiFrequencyDescriptorEngine,
    ScheduleDescriptor,
)
from app.core.cron.relative_delay_parser import RelativeDelayParser

logger = logging.getLogger(__name__)


class UniversalVisualScheduler:
    """通用可视化时间调度器引擎。"""

    def __init__(
        self,
        *,
        ledger: LifecycleArchiveLedger | None = None,
        on_bot_active_changed: Callable[[str, bool], None] | None = None,
    ) -> None:
        self._ledger = ledger or LifecycleArchiveLedger(on_bot_active_changed=on_bot_active_changed)
        self._task_actions: dict[str, Callable[[], Awaitable[None]]] = {}

    @property
    def ledger(self) -> LifecycleArchiveLedger:
        """底层生命周期归档账本。"""
        return self._ledger

    def schedule_relative_task(
        self,
        task_name: str,
        bot_id: str,
        relative_expr: str,
        *,
        action: Callable[[], Awaitable[None]] | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        """快速注册一次性相对延迟任务（如 '5m', '30分钟后', '明天上午09:00'）。"""
        now = time.time()
        parsed = RelativeDelayParser.parse(relative_expr, base_time=now)
        descriptor = ScheduleDescriptor(
            kind=FrequencyKind.ONCE_RELATIVE,
            relative_expression=relative_expr,
            absolute_timestamp=parsed.execute_at_timestamp,
        )
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        record = self._ledger.register_task(
            task_id=tid,
            task_name=task_name,
            bot_id=bot_id,
            descriptor=descriptor,
            next_run_at=parsed.execute_at_timestamp,
        )
        if action is not None:
            self._task_actions[tid] = action
        return record

    def schedule_recurring_task(
        self,
        task_name: str,
        bot_id: str,
        descriptor: ScheduleDescriptor,
        *,
        action: Callable[[], Awaitable[None]] | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        """注册多频周期性调度任务（每小时/每天/工作日/每周/每月）。"""
        now = time.time()
        next_run = MultiFrequencyDescriptorEngine.compute_next_run(descriptor, now)
        if next_run is None:
            raise ValueError("Failed to compute valid next run time for recurring task descriptor.")

        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        record = self._ledger.register_task(
            task_id=tid,
            task_name=task_name,
            bot_id=bot_id,
            descriptor=descriptor,
            next_run_at=next_run,
        )
        if action is not None:
            self._task_actions[tid] = action
        return record

    def cancel_task(self, task_id: str) -> TaskRecord:
        """取消活跃任务并移入归档区。"""
        record = self._ledger.cancel_task(task_id)
        self._task_actions.pop(task_id, None)
        return record

    async def execute_task_once(self, task_id: str) -> TaskRecord:
        """执行指定任务单次执行周期，并根据类型自动归档或排期下一轮。"""
        record = self._ledger.get_task(task_id)
        self._ledger.record_task_start(task_id)
        action = self._task_actions.get(task_id)

        try:
            if action is not None:
                await action()
            now = time.time()

            # 若是一次性任务，计算下轮为 None -> 触发自愈归档
            next_run: float | None = None
            if not record.is_one_off:
                next_run = MultiFrequencyDescriptorEngine.compute_next_run(record.descriptor, now)

            completed = self._ledger.record_task_completed(task_id, next_cycle_run_at=next_run)
            if completed.is_one_off:
                self._task_actions.pop(task_id, None)
            return completed

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Task execution failed for '%s': %s", task_id, error_msg)
            failed = self._ledger.record_task_failed(task_id, error_message=error_msg)
            if failed.is_one_off:
                self._task_actions.pop(task_id, None)
            return failed

    async def trigger_now(self, task_id: str) -> TaskRecord:
        """手动立即触发执行任务一次。"""
        return await self.execute_task_once(task_id)

    async def process_due_tasks(self, *, now: float | None = None) -> list[str]:
        """扫描并并发执行所有已到期（next_run_at <= now）的活跃任务。"""
        current_time = now if now is not None else time.time()
        active = self._ledger.list_active_tasks()
        due_tasks = [t for t in active if t.next_run_at <= current_time]

        executed_ids: list[str] = []
        coros: list[asyncio.Task[TaskRecord]] = []
        for task in due_tasks:
            executed_ids.append(task.task_id)
            coros.append(asyncio.create_task(self.execute_task_once(task.task_id)))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

        return executed_ids

    def get_task(self, task_id: str) -> TaskRecord:
        """获取任务详情。"""
        return self._ledger.get_task(task_id)

    def list_active_tasks(self) -> tuple[TaskRecord, ...]:
        """获取当前待执行的活跃任务列表。"""
        return self._ledger.list_active_tasks()

    def list_archived_tasks(self) -> tuple[TaskRecord, ...]:
        """获取已完成/已归档的历史任务列表。"""
        return self._ledger.list_archived_tasks()
