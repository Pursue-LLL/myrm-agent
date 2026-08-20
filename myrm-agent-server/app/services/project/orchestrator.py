"""
[INPUT] asyncio.Lock (POS: 异步并发锁)
[OUTPUT] ProjectOrchestrator: 项目级并发调度器
[POS] 项目并发控制。确保同一个项目的多个 Agent 不会并发修改工作区文件。
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class ProjectOrchestrator:
    """项目级并发调度器

    使用异步锁确保同一个 Project 下的多个 Agent 是回合制执行的，
    避免并发读写同一个 workspace_path 导致文件损坏或进程冲突（如并发 npm install）。
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, project_id: str) -> asyncio.Lock:
        """获取指定项目的并发锁（首次访问创建并缓存）"""
        lock = self._locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[project_id] = lock
        return lock

    async def acquire(self, project_id: str) -> None:
        """申请项目锁"""
        logger.debug(f"Acquiring lock for project {project_id}")
        await self.get_lock(project_id).acquire()
        logger.debug(f"Lock acquired for project {project_id}")

    def release(self, project_id: str) -> None:
        """释放项目锁；锁无持有者且无等待者时从缓存移除"""
        lock = self._locks.get(project_id)
        if lock is not None and lock.locked():
            lock.release()
            logger.debug(f"Lock released for project {project_id}")
            if not lock.locked() and not lock._waiters:
                self._locks.pop(project_id, None)
            elif not lock.locked():
                # 存在 waiter：它在下一个事件循环 tick 才会真正接管锁。
                # 若届时已被取消（`_acquire_guarded` 的 wait_for 超时路径），
                # 锁将永久空闲但无后续 release 触发清理 → 缓存残留。
                # 延迟到 tick 后复检，堵住取消路径的残留。
                self._schedule_idle_cleanup(project_id, lock)

    def _schedule_idle_cleanup(self, project_id: str, lock: asyncio.Lock) -> None:
        """下一个事件循环 tick 检查锁是否彻底空闲并清理缓存。

        直接 pop 的时序不可靠：``release`` 唤醒了等待者，但等待者的
        ``acquire`` 要到下一个 tick 才会从 ``_waiters`` 移除并接管锁。
        若等待者已被取消，锁从此空闲但无释放点，缓存会永久残留。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if not lock.locked() and not lock._waiters:
                self._locks.pop(project_id, None)
            return

        def _cleanup() -> None:
            if self._locks.get(project_id) is lock and not lock.locked() and not lock._waiters:
                self._locks.pop(project_id, None)

        loop.call_soon(_cleanup)

    def is_locked(self, project_id: str) -> bool:
        """检查项目是否被锁定（纯查询，不创建锁）"""
        lock = self._locks.get(project_id)
        return lock.locked() if lock is not None else False

    def forget(self, project_id: str) -> None:
        """项目删除时清理锁缓存；锁被持有或等待时不强制移除"""
        lock = self._locks.get(project_id)
        if lock is not None and not lock.locked() and not lock._waiters:
            self._locks.pop(project_id, None)


# 全局单例
project_orchestrator = ProjectOrchestrator()
