"""
[INPUT] asyncio.Lock (POS: 异步并发锁)
[OUTPUT] ProjectOrchestrator: 项目级并发调度器
[POS] 项目并发控制。确保同一个项目的多个 Agent 不会并发修改工作区文件。
"""

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class ProjectOrchestrator:
    """项目级并发调度器
    
    使用异步锁确保同一个 Project 下的多个 Agent 是回合制执行的，
    避免并发读写同一个 workspace_path 导致文件损坏或进程冲突（如并发 npm install）。
    """
    
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        
    def get_lock(self, project_id: str) -> asyncio.Lock:
        """获取指定项目的并发锁"""
        return self._locks[project_id]
        
    async def acquire(self, project_id: str) -> None:
        """申请项目锁"""
        logger.debug(f"Acquiring lock for project {project_id}")
        await self.get_lock(project_id).acquire()
        logger.debug(f"Lock acquired for project {project_id}")
        
    def release(self, project_id: str) -> None:
        """释放项目锁"""
        lock = self.get_lock(project_id)
        if lock.locked():
            lock.release()
            logger.debug(f"Lock released for project {project_id}")
            
    def is_locked(self, project_id: str) -> bool:
        """检查项目是否被锁定"""
        return self.get_lock(project_id).locked()

# 全局单例
project_orchestrator = ProjectOrchestrator()
