"""租约心跳服务与执行守卫上下文。

提供周期性租约自动续约，若续约失败或 Fencing Token 失效则触发快速熔断，
杜绝僵死 Worker 产生脏写入。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.job.store import JobStore

logger = logging.getLogger(__name__)


class LeaseLostError(Exception):
    """当租约无法续约或 Fencing Token 发生冲突时抛出。"""


class LeaseHeartbeatService:
    """租约后台自动续约服务。"""

    def __init__(
        self,
        store: JobStore,
        segment_id: str,
        fencing_token: int,
        lease_seconds: float = 120.0,
        interval_seconds: float = 30.0,
    ) -> None:
        self._store = store
        self._segment_id = segment_id
        self._fencing_token = fencing_token
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task[None]] = None
        self._lost_event = asyncio.Event()
        self._stop_event = asyncio.Event()

    @property
    def is_lost(self) -> bool:
        """检查租约是否已被夺取或失效。"""
        return self._lost_event.is_set()

    def check_alive(self) -> None:
        """主动检查租约存活，若已丢失立即抛出熔断异常。"""
        if self.is_lost:
            raise LeaseLostError(
                f"Lease lost for segment {self._segment_id} (token={self._fencing_token})"
            )

    async def start(self) -> None:
        """启动后台心跳续约协程。"""
        if self._task is not None:
            return
        self._stop_event.clear()
        self._lost_event.clear()
        self._task = asyncio.create_task(self._run_heartbeat())

    async def stop(self) -> None:
        """停止心跳协程并等待其安全退出。"""
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run_heartbeat(self) -> None:
        """周期心跳续约循环。"""
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._interval_seconds)
                if self._stop_event.is_set():
                    break

                renewed = await self._store.renew_lease(
                    segment_id=self._segment_id,
                    fencing_token=self._fencing_token,
                    lease_seconds=self._lease_seconds,
                )
                if not renewed:
                    logger.warning(
                        "Heartbeat renewal rejected for segment %s with token %d",
                        self._segment_id,
                        self._fencing_token,
                    )
                    self._lost_event.set()
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Unexpected error during lease renewal: %s", exc)
            self._lost_event.set()


class LeaseContext:
    """切片执行租约上下文管理器。

    用法：
        async with LeaseContext(store, segment_id, fencing_token) as lease:
            lease.check_alive()
            # 执行切片步骤...
    """

    def __init__(
        self,
        store: JobStore,
        segment_id: str,
        fencing_token: int,
        lease_seconds: float = 120.0,
        interval_seconds: float = 30.0,
    ) -> None:
        self._service = LeaseHeartbeatService(
            store=store,
            segment_id=segment_id,
            fencing_token=fencing_token,
            lease_seconds=lease_seconds,
            interval_seconds=interval_seconds,
        )

    async def __aenter__(self) -> LeaseHeartbeatService:
        await self._service.start()
        return self._service

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        await self._service.stop()
        if exc_val is None and self._service.is_lost:
            raise LeaseLostError("Lease expired during task execution")
