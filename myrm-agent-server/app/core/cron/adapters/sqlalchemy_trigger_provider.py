"""SQLAlchemy implementation of the TriggerProvider protocol.

[INPUT]
myrm_agent_harness.toolkits.cron.protocols::TriggerProvider (POS: 事件/Webhook/系统事件触发器匹配协议)
myrm_agent_harness.toolkits.cron.triggers (POS: 触发器类型定义与安全工具)
app.database.models::CronJobModel (POS: 定时任务 ORM 模型)
app.core.cron.adapters.sqlalchemy_mapping::job_to_domain (POS: ORM <-> Domain 映射)

[OUTPUT]
SqlAlchemyTriggerProvider: 从数据库查询并匹配触发器的 TriggerProvider 实现

[POS]
数据库驱动的触发器匹配。从 CronJobModel 查询配置了 triggers 的活跃任务，
执行 event regex/system_event/webhook 匹配逻辑。
"""

from __future__ import annotations

import logging
import re

from myrm_agent_harness.toolkits.cron.triggers import validate_regex_pattern, validate_webhook_secret
from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus
from sqlalchemy import select

from app.core.cron.adapters.sqlalchemy_mapping import job_to_domain
from app.database.connection import get_session
from app.database.models import CronJobModel

logger = logging.getLogger(__name__)


class SqlAlchemyTriggerProvider:
    """TriggerProvider backed by SQLAlchemy.

    Queries active cron jobs that have trigger configs and performs
    in-memory matching against the provided event data.
    """

    async def _load_triggered_jobs(self) -> list[CronJob]:
        """Load all active jobs that have trigger configurations."""
        async with get_session() as session:
            stmt = select(CronJobModel).where(
                CronJobModel.status == JobStatus.ACTIVE,
                CronJobModel.triggers.isnot(None),
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [job_to_domain(r) for r in rows]

    async def check_event_triggers(
        self,
        message: str,
        channel: str,
        user_id: str,
    ) -> list[CronJob]:
        """Return jobs whose event triggers match the incoming message."""
        jobs = await self._load_triggered_jobs()
        matched: list[CronJob] = []

        for job in jobs:
            if not job.triggers or not job.triggers.events:
                continue

            for event in job.triggers.events:
                if event.channel and event.channel != channel:
                    continue
                try:
                    compiled = validate_regex_pattern(event.pattern, max_bytes=event.max_pattern_bytes)
                    if compiled.search(message):
                        matched.append(job)
                        break
                except (re.error, ValueError) as exc:
                    logger.warning(
                        "Invalid regex in job %s event trigger: %s",
                        job.id,
                        exc,
                    )

        return matched

    async def check_system_event(
        self,
        source: str,
        event_type: str,
        payload: dict[str, object],
    ) -> list[CronJob]:
        """Return jobs whose system-event triggers match the event."""
        jobs = await self._load_triggered_jobs()
        matched: list[CronJob] = []

        for job in jobs:
            if not job.triggers or not job.triggers.system_events:
                continue

            for se in job.triggers.system_events:
                if se.source != source or se.event_type != event_type:
                    continue
                if all(str(payload.get(k)) == v for k, v in se.filters.items()):
                    matched.append(job)
                    break

        return matched

    async def handle_webhook(
        self,
        path: str,
        secret: str,
        payload: dict[str, object],
    ) -> CronJob | None:
        """Validate and return the job matching the webhook path + secret."""
        jobs = await self._load_triggered_jobs()

        for job in jobs:
            if not job.triggers or not job.triggers.webhooks:
                continue

            for wh in job.triggers.webhooks:
                if wh.path != path:
                    continue
                if wh.secret and not validate_webhook_secret(wh.secret, secret):
                    logger.warning("Webhook secret mismatch for job %s", job.id)
                    continue
                return job

        return None
