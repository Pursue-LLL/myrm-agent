"""Global Baseline Sync (Pull Model Client)

⚠️ Phase 2.3: 全局基线同步
解决单机沙箱的“信息孤岛”和“冷启动”问题。
Server 启动时或定期从控制平面拉取全局高分 Skill 列表，注入 Harness。
"""

import asyncio
import logging

import httpx

from app.config.settings import settings
from app.core.infra.server_globals import get_optimization_scheduler
from app.schemas.control_plane import BaselinesResponse

logger = logging.getLogger(__name__)


class BaselineSyncer:
    """全局基线同步器"""

    def __init__(self, control_plane_url: str | None = None) -> None:
        cp = settings.control_plane
        self.control_plane_url = control_plane_url or cp.effective_url()
        self.sync_interval_seconds = cp.baseline_sync_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动后台同步任务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._sync_loop())
        logger.info(f"BaselineSyncer started. Syncing from {self.control_plane_url} every {self.sync_interval_seconds}s")

    async def stop(self) -> None:
        """停止后台同步任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BaselineSyncer stopped.")

    async def _sync_loop(self) -> None:
        """同步循环"""
        while self._running:
            try:
                await self.sync_baselines()
            except Exception as e:
                logger.error(f"Failed to sync baselines: {e}")

            # Sleep for the interval, but check self._running periodically
            for _ in range(self.sync_interval_seconds):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def sync_baselines(self) -> None:
        """执行一次同步"""
        endpoint = f"{self.control_plane_url}/api/telemetry/baselines/skills"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(endpoint)
                response.raise_for_status()
                raw = response.json()
                baselines_resp = BaselinesResponse.model_validate(raw)
                baselines = baselines_resp.baselines
                logger.info(f"Successfully fetched {len(baselines)} global baselines.")

                # Apply baselines to local Harness storage
                scheduler = get_optimization_scheduler()
                if scheduler and hasattr(scheduler, "execution_provider"):
                    # We need a way to inject this into Harness.
                    # For now, we can log it or save it to a local cache.
                    # In a full implementation, the ExecutionProvider or a dedicated BaselineProvider
                    # would use this data when evaluating skills.
                    logger.debug(f"Global baselines ready for injection: {baselines}")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching baselines: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Network error fetching baselines from {endpoint}: {e}")


# Global instance
_baseline_syncer = None


def get_baseline_syncer() -> BaselineSyncer:
    global _baseline_syncer
    if _baseline_syncer is None:
        _baseline_syncer = BaselineSyncer()
    return _baseline_syncer
