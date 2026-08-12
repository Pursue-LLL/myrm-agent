"""Skill Permission Usage Logger

业务层的权限使用日志记录服务。
注册到框架层作为callback，将log写入数据库。
"""

import asyncio
import logging
from queue import Queue
from threading import Thread
from typing import TypedDict

from app.database.connection import get_session
from app.database.models import SkillPermissionUsageLog

logger = logging.getLogger(__name__)


class _PermissionLogItem(TypedDict):
    user_id: str
    skill_id: str
    permission: str
    operation: str
    allowed: bool
    deny_reason: str


# 日志队列（异步写入避免阻塞）
_log_queue: Queue[_PermissionLogItem] | None = None
_log_worker_thread: Thread | None = None
_shutdown_flag = False


def _log_worker() -> None:
    """后台线程：批量写入日志到数据库"""
    global _shutdown_flag
    batch: list[_PermissionLogItem] = []
    batch_size = 10
    flush_interval = 5.0

    import time

    last_flush = time.time()

    while not _shutdown_flag:
        try:
            if _log_queue:
                try:
                    item = _log_queue.get(timeout=1.0)
                    batch.append(item)

                    if len(batch) >= batch_size or (time.time() - last_flush) >= flush_interval:
                        _flush_batch(batch)
                        batch.clear()
                        last_flush = time.time()

                except Exception:
                    if batch:
                        _flush_batch(batch)
                        batch.clear()
                        last_flush = time.time()
        except Exception as e:
            logger.error(f"Log worker error: {e}", exc_info=True)

    if batch:
        _flush_batch(batch)


def _flush_batch(batch: list[_PermissionLogItem]) -> None:
    """批量写入数据库"""
    if not batch:
        return

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_flush_batch(batch))
        loop.close()
    except Exception as e:
        logger.error(f"Failed to flush log batch: {e}", exc_info=True)


async def _async_flush_batch(batch: list[_PermissionLogItem]) -> None:
    """异步批量写入"""
    async with get_session() as session:
        for log_data in batch:
            log = SkillPermissionUsageLog(
                user_id=log_data["user_id"],
                skill_id=log_data["skill_id"],
                permission=log_data["permission"],
                operation=log_data["operation"],
                allowed=log_data["allowed"],
                deny_reason=log_data["deny_reason"],
            )
            session.add(log)
        await session.commit()
        logger.debug(f"Flushed {len(batch)} permission usage logs")


def permission_usage_callback(
    user_id: str,
    skill_id: str,
    permission: str,
    operation: str,
    allowed: bool,
    deny_reason: str,
) -> None:
    """框架层回调函数

    由框架层的log_permission_usage调用。
    将日志数据放入队列，由后台线程批量写入数据库。
    """
    if _log_queue:
        _log_queue.put(
            {
                "user_id": user_id,
                "skill_id": skill_id,
                "permission": permission,
                "operation": operation,
                "allowed": allowed,
                "deny_reason": deny_reason,
            }
        )
    else:
        logger.warning("Permission usage queue not initialized, skipping log")


def start_permission_logger() -> None:
    """启动权限日志记录服务"""
    global _log_queue, _log_worker_thread, _shutdown_flag

    if _log_queue is not None:
        logger.warning("Permission logger already started")
        return

    _log_queue = Queue()
    _shutdown_flag = False
    _log_worker_thread = Thread(target=_log_worker, daemon=True)
    _log_worker_thread.start()

    # 注册到框架层
    from myrm_agent_harness.backends.skills import set_permission_usage_callback

    def callback_wrapper(skill_id: str, permission: str, operation: str, allowed: bool, deny_reason: str) -> None:
        # 框架层不知道user_id，业务层从上下文获取
        # 这里使用"unknown"作为默认值，实际应该从请求上下文获取
        permission_usage_callback("unknown", skill_id, permission, operation, allowed, deny_reason)

    set_permission_usage_callback(callback_wrapper)
    logger.info("Permission logger started")


def stop_permission_logger() -> None:
    """停止权限日志记录服务"""
    global _shutdown_flag, _log_worker_thread, _log_queue

    if _log_queue is None:
        return

    _shutdown_flag = True
    if _log_worker_thread:
        _log_worker_thread.join(timeout=5.0)
        _log_worker_thread = None

    _log_queue = None
    logger.info("Permission logger stopped")
