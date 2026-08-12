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
