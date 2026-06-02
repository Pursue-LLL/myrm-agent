"""Telemetry Pusher (Push Model Client)

⚠️ Phase 2.2: 遥测推模式客户端
解决控制平面的扩展性灾难。
Server 增加一个后台定时任务，定期将脱敏的 Skill 质量数据 POST 推送到控制平面。
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.adapters.skill_optimization.quality_repo import QualityRepository
from app.config.settings import settings
from app.platform_utils import get_session_factory
from app.schemas.control_plane import SkillQualityTelemetry, TelemetryPushPayload

logger = logging.getLogger(__name__)


class TelemetryPusher:
    """遥测数据推送器"""

    def __init__(self, control_plane_url: str | None = None, tenant_id: str | None = None) -> None:
        cp = settings.control_plane
        self.control_plane_url = control_plane_url or cp.effective_url()
        self.tenant_id = tenant_id or cp.tenant_id
        self.push_interval_seconds = cp.telemetry_push_interval
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动后台推送任务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._push_loop())
        logger.info(f"TelemetryPusher started. Pushing to {self.control_plane_url} every {self.push_interval_seconds}s")

    async def stop(self) -> None:
        """停止后台推送任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TelemetryPusher stopped.")

    async def _push_loop(self) -> None:
        """推送循环"""
        while self._running:
            try:
                await self._push_telemetry()
            except Exception as e:
                logger.error(f"Failed to push telemetry: {e}")

            # Sleep for the interval, but check self._running periodically
            for _ in range(self.push_interval_seconds):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def _push_telemetry(self) -> None:
        """执行一次推送"""
        session_factory = get_session_factory()
        skills_payload: list[SkillQualityTelemetry] = []

        async with session_factory() as session:
            repo = QualityRepository(session)
            latest_qualities = await repo.get_all_latest_qualities()

            if not latest_qualities:
                logger.debug("No telemetry data to push.")
                return

            for skill_id, quality_dict in latest_qualities.items():
                skills_payload.append(
                    SkillQualityTelemetry(
                        skill_id=skill_id,
                        overall_score=quality_dict.get("overall_score", 0.0),
                        success_rate=quality_dict.get("success_rate", 0.0),
                        execution_time=quality_dict.get("execution_time", 0.0),
                        call_frequency=quality_dict.get("call_frequency", 0.0),
                    )
                )

        payload = TelemetryPushPayload(
            tenant_id=self.tenant_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            skills=skills_payload,
        )

        endpoint = f"{self.control_plane_url}/api/telemetry/skill-quality"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(endpoint, json=payload.model_dump())
                response.raise_for_status()
                logger.info(f"Successfully pushed telemetry for {len(skills_payload)} skills.")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error pushing telemetry: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Network error pushing telemetry to {endpoint}: {e}")


# Global instance
_telemetry_pusher = None


def get_telemetry_pusher() -> TelemetryPusher:
    global _telemetry_pusher
    if _telemetry_pusher is None:
        _telemetry_pusher = TelemetryPusher()
    return _telemetry_pusher
