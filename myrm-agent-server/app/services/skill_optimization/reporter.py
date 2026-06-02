"""Skill Usage Reporter

Generate quality reports for skill optimization.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
    from myrm_agent_harness.agent.skills.optimization import SkillQualityScore
    from myrm_agent_harness.agent.skills.optimization.quality_calculator import (
        SkillExecutionSample,
    )
    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)


class SkillUsageReporter:
    """Skill使用报告生成器

    从EventLog获取skill执行历史，生成质量报告。
    """

    def __init__(self, event_log_backend: "EventLogBackend | None" = None):
        """初始化Reporter

        Args:
            event_log_backend: EventLog后端（可选）
        """
        self.event_log_backend = event_log_backend

    async def generate_quality_report(
        self,
        skill: "SkillMetadata",
        quality_score: "SkillQualityScore",
    ) -> dict[str, object]:
        """生成skill质量报告

        Args:
            skill: Skill元数据
            quality_score: 质量评分

        Returns:
            dict: 质量报告
        """
        return {
            "skill_id": skill.name,
            "skill_name": skill.name,
            "description": skill.description,
            "quality_score": {
                "success_rate": quality_score.success_rate,
                "token_efficiency": quality_score.token_efficiency,
                "execution_time": quality_score.execution_time,
                "user_satisfaction": quality_score.user_satisfaction,
                "call_frequency": quality_score.call_frequency,
                "overall": quality_score.overall_score,
            },
            "recommendation": self._generate_recommendation(quality_score),
        }

    def _generate_recommendation(self, quality_score: "SkillQualityScore") -> str:
        """生成优化建议"""
        if quality_score.overall_score >= 0.8:
            return "Excellent quality, no optimization needed"
        elif quality_score.overall_score >= 0.6:
            return "Good quality, minor improvements possible"
        else:
            return "Low quality, optimization recommended"

    async def get_top_skills(self, limit: int = 10) -> list[dict[str, object]]:
        """Get top N skills by quality score. Returns empty if no data."""
        return []

    async def get_bottom_skills(self, limit: int = 10) -> list[dict[str, object]]:
        """Get bottom N skills by quality score. Returns empty if no data."""
        return []

    async def get_skill_execution_samples(
        self,
        skill_id: str,
        days: int = 7,
        session_id: str | None = None,
    ) -> list["SkillExecutionSample"]:
        """从EventLog查询skill执行历史

        Args:
            skill_id: Skill ID
            days: 查询天数
            session_id: 会话ID（可选）

        Returns:
            list[SkillExecutionSample]: 执行样本列表
        """
        if not self.event_log_backend:
            logger.warning("EventLog backend not available")
            return []

        from myrm_agent_harness.agent.event_log.types import EventFilter
        from myrm_agent_harness.agent.skills.optimization.quality_calculator import (
            SkillExecutionSample,
        )

        start_time = datetime.now() - timedelta(days=days)
        start_timestamp = start_time.timestamp()

        event_filter = EventFilter(
            event_types=frozenset(["tool_start", "tool_complete", "tool_error"]),
            start_time=start_timestamp,
        )

        if session_id:
            events = await self.event_log_backend.get_events(session_id=session_id, event_filter=event_filter)
        else:
            all_sessions = await self.event_log_backend.list_sessions()
            events = []
            for sid in all_sessions[:50]:
                session_events = await self.event_log_backend.get_events(session_id=sid, event_filter=event_filter)
                events.extend(session_events)

        samples: list[SkillExecutionSample] = []
        tool_executions: dict[str, dict[str, object]] = {}

        for event in events:
            event_data = event.data
            tool_name = event_data.get("tool_name", "")

            if not tool_name.startswith(f"skill_{skill_id}"):
                continue

            tool_call_id = event_data.get("tool_call_id", "")

            if event.event_type == "tool_start":
                tool_executions[tool_call_id] = {
                    "start_time": event.timestamp,
                    "tool_name": tool_name,
                }

            elif event.event_type in ["tool_complete", "tool_error"]:
                if tool_call_id in tool_executions:
                    exec_info = tool_executions[tool_call_id]
                    execution_time = event.timestamp - exec_info["start_time"]

                    sample = SkillExecutionSample(
                        skill_id=skill_id,
                        success=(event.event_type == "tool_complete"),
                        tokens_used=event_data.get("tokens_used", 0),
                        execution_time=execution_time,
                        user_feedback=event_data.get("user_feedback"),
                        timestamp=datetime.fromtimestamp(event.timestamp),
                    )
                    samples.append(sample)

                    del tool_executions[tool_call_id]

        logger.info(f"Retrieved {len(samples)} execution samples for skill {skill_id}")
        return samples
