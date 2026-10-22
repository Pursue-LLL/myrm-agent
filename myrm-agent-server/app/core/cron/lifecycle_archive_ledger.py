"""一次性任务生命周期治理、自愈自动归档与智能体活跃解绑账本模块。

提供任务全生命周期状态机管理（PENDING -> RUNNING -> COMPLETED/FAILED -> ARCHIVED），
针对一次性延迟任务，执行完毕即刻从活跃调度堆弹出并转入归档折叠区，
同时联动解除关联 Bot 的呼吸活跃徽章，彻底消除任务垃圾数据膨胀与僵尸活跃状态。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from app.core.cron.multi_frequency_descriptor import FrequencyKind, ScheduleDescriptor

logger = logging.getLogger(__name__)


class TaskLifecycleStatus(StrEnum):
    """任务生命周期状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """任务全生命周期元数据实体。"""

    task_id: str
    task_name: str
    bot_id: str
    descriptor: ScheduleDescriptor
    status: TaskLifecycleStatus
    created_at: float
    next_run_at: float
    last_run_at: float | None = None
    completed_at: float | None = None
    retry_count: int = 0
    error_message: str | None = None
    is_one_off: bool = False


class TaskLedgerError(Exception):
    """账本基础异常。"""


class TaskNotFoundError(TaskLedgerError):
    """任务未找到异常。"""


class LifecycleArchiveLedger:
    """一次性与多频任务生命周期自愈归档账本。"""

    def __init__(
        self,
        *,
        on_bot_active_changed: Callable[[str, bool], None] | None = None,
    ) -> None:
        self._on_bot_active_changed = on_bot_active_changed
        self._active_tasks: dict[str, TaskRecord] = {}
        self._archived_tasks: dict[str, TaskRecord] = {}

    def _notify_bot_state(self, bot_id: str, is_active: bool) -> None:
        """安全通知关联智能体活跃状态变更。"""
        if self._on_bot_active_changed is not None:
            try:
                self._on_bot_active_changed(bot_id, is_active)
            except Exception as exc:
                logger.error("Failed to notify bot '%s' activity change: %s", bot_id, exc)

    def register_task(
        self,
        task_id: str,
        task_name: str,
        bot_id: str,
        descriptor: ScheduleDescriptor,
        next_run_at: float,
    ) -> TaskRecord:
        """注册新调度任务进活跃队列。"""
        is_one_off = descriptor.kind in (
            FrequencyKind.ONCE_RELATIVE,
            FrequencyKind.ONCE_ABSOLUTE,
        )
        now = time.time()
        record = TaskRecord(
            task_id=task_id,
            task_name=task_name,
            bot_id=bot_id,
            descriptor=descriptor,
            status=TaskLifecycleStatus.PENDING,
            created_at=now,
            next_run_at=next_run_at,
            last_run_at=None,
            completed_at=None,
            retry_count=0,
            error_message=None,
            is_one_off=is_one_off,
        )
        self._active_tasks[task_id] = record
        return record

    def record_task_start(self, task_id: str) -> TaskRecord:
        """标记任务开始执行，点亮关联 Bot 活跃呼吸态。"""
        record = self._active_tasks.get(task_id)
        if record is None:
            raise TaskNotFoundError(f"Active task '{task_id}' not found.")

        now = time.time()
        updated = TaskRecord(
            task_id=record.task_id,
            task_name=record.task_name,
            bot_id=record.bot_id,
            descriptor=record.descriptor,
            status=TaskLifecycleStatus.RUNNING,
            created_at=record.created_at,
            next_run_at=record.next_run_at,
            last_run_at=now,
            completed_at=None,
            retry_count=record.retry_count,
            error_message=None,
            is_one_off=record.is_one_off,
        )
        self._active_tasks[task_id] = updated
        # 激活关联 Bot 动态呼吸动画
        self._notify_bot_state(record.bot_id, True)
        return updated

    def record_task_completed(
        self,
        task_id: str,
        *,
        next_cycle_run_at: float | None = None,
    ) -> TaskRecord:
        """记录任务成功执行完成。

        若为一次性任务，自动从活跃堆弹出，状态置为 COMPLETED，移入归档区并解绑 Bot 活跃态。
        若为周期性任务，更新下一次触发时间并恢复 PENDING，解除单次运行活跃态。
        """
        record = self._active_tasks.get(task_id)
        if record is None:
            raise TaskNotFoundError(f"Active task '{task_id}' not found.")

        now = time.time()

        # 1. 一次性任务：执行完毕即刻自愈归档，杜绝僵尸数据
        if record.is_one_off or next_cycle_run_at is None:
            completed_record = TaskRecord(
                task_id=record.task_id,
                task_name=record.task_name,
                bot_id=record.bot_id,
                descriptor=record.descriptor,
                status=TaskLifecycleStatus.COMPLETED,
                created_at=record.created_at,
                next_run_at=record.next_run_at,
                last_run_at=record.last_run_at,
                completed_at=now,
                retry_count=record.retry_count,
                error_message=None,
                is_one_off=True,
            )
            # 事务级弹出活跃堆并存入归档账本
            del self._active_tasks[task_id]
            self._archived_tasks[task_id] = completed_record

            # 解除 Bot 活跃呼吸态
            self._notify_bot_state(record.bot_id, False)
            return completed_record

        # 2. 周期性任务：流转回 PENDING 并排期下一次运行
        recurring_record = TaskRecord(
            task_id=record.task_id,
            task_name=record.task_name,
            bot_id=record.bot_id,
            descriptor=record.descriptor,
            status=TaskLifecycleStatus.PENDING,
            created_at=record.created_at,
            next_run_at=next_cycle_run_at,
            last_run_at=record.last_run_at,
            completed_at=now,
            retry_count=0,
            error_message=None,
            is_one_off=False,
        )
        self._active_tasks[task_id] = recurring_record
        self._notify_bot_state(record.bot_id, False)
        return recurring_record

    def record_task_failed(
        self,
        task_id: str,
        error_message: str,
        *,
        can_retry: bool = False,
        retry_next_at: float | None = None,
    ) -> TaskRecord:
        """记录任务执行失败。若不可重试且为一次性任务，自动移入归档区。"""
        record = self._active_tasks.get(task_id)
        if record is None:
            raise TaskNotFoundError(f"Active task '{task_id}' not found.")

        now = time.time()
        retries = record.retry_count + 1

        if can_retry and retry_next_at is not None:
            retry_record = TaskRecord(
                task_id=record.task_id,
                task_name=record.task_name,
                bot_id=record.bot_id,
                descriptor=record.descriptor,
                status=TaskLifecycleStatus.PENDING,
                created_at=record.created_at,
                next_run_at=retry_next_at,
                last_run_at=record.last_run_at,
                completed_at=None,
                retry_count=retries,
                error_message=error_message,
                is_one_off=record.is_one_off,
            )
            self._active_tasks[task_id] = retry_record
            self._notify_bot_state(record.bot_id, False)
            return retry_record

        # 不可重试或重试耗尽
        failed_record = TaskRecord(
            task_id=record.task_id,
            task_name=record.task_name,
            bot_id=record.bot_id,
            descriptor=record.descriptor,
            status=TaskLifecycleStatus.FAILED,
            created_at=record.created_at,
            next_run_at=record.next_run_at,
            last_run_at=record.last_run_at,
            completed_at=now,
            retry_count=retries,
            error_message=error_message,
            is_one_off=record.is_one_off,
        )

        if record.is_one_off:
            del self._active_tasks[task_id]
            self._archived_tasks[task_id] = failed_record
        else:
            self._active_tasks[task_id] = failed_record

        self._notify_bot_state(record.bot_id, False)
        return failed_record

    def cancel_task(self, task_id: str) -> TaskRecord:
        """取消活跃任务并移入归档区。"""
        record = self._active_tasks.get(task_id)
        if record is None:
            raise TaskNotFoundError(f"Active task '{task_id}' not found.")

        now = time.time()
        cancelled_record = TaskRecord(
            task_id=record.task_id,
            task_name=record.task_name,
            bot_id=record.bot_id,
            descriptor=record.descriptor,
            status=TaskLifecycleStatus.CANCELLED,
            created_at=record.created_at,
            next_run_at=record.next_run_at,
            last_run_at=record.last_run_at,
            completed_at=now,
            retry_count=record.retry_count,
            error_message="User cancelled task",
            is_one_off=record.is_one_off,
        )
        del self._active_tasks[task_id]
        self._archived_tasks[task_id] = cancelled_record
        self._notify_bot_state(record.bot_id, False)
        return cancelled_record

    def get_task(self, task_id: str) -> TaskRecord:
        """查询任务（优先从活跃区查找，再从归档区查找）。"""
        if task_id in self._active_tasks:
            return self._active_tasks[task_id]
        if task_id in self._archived_tasks:
            return self._archived_tasks[task_id]
        raise TaskNotFoundError(f"Task '{task_id}' not found in ledger.")

    def list_active_tasks(self) -> tuple[TaskRecord, ...]:
        """按下次执行时间升序返回所有当前活跃任务。"""
        return tuple(sorted(self._active_tasks.values(), key=lambda t: t.next_run_at))

    def list_archived_tasks(self) -> tuple[TaskRecord, ...]:
        """按完成时间倒序返回已完成/已归档的历史任务。"""
        return tuple(
            sorted(
                self._archived_tasks.values(),
                key=lambda t: t.completed_at or 0.0,
                reverse=True,
            )
        )

    def clean_expired_archives(self, max_age_seconds: float) -> int:
        """清理超出生命周期的历史归档，防止内存或持久化数据无界膨胀。"""
        now = time.time()
        expired_ids = [
            tid
            for tid, record in self._archived_tasks.items()
            if record.completed_at is not None and (now - record.completed_at) > max_age_seconds
        ]
        for tid in expired_ids:
            del self._archived_tasks[tid]
        return len(expired_ids)
