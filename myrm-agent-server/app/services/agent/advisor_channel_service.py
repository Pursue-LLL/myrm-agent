"""
[INPUT]
- typing (Optional)
- myrm_agent_harness.agent.sub_agents.advisor_channel (
    DualModelAdvisorEngine,
    get_default_advisor_engine,
  )
- app.schemas.advisor_channel (
    AdvisorInterventionDTO,
    AdvisorReviewResultDTO,
    AdvisorReviewStepRequestDTO,
    AdvisorSessionReviewsResponseDTO,
  )

[OUTPUT]
- AdvisorChannelService: 双模型实时旁路军师评审业务服务
- get_advisor_channel_service: 获取单例治理服务实例工厂

[POS]
Server 业务层双模型实时旁路军师评审通道服务（Topic 12 · 第 17 项）。
聚合 Harness 框架层 DualModelAdvisorEngine，维护会话级审查历史，提供 aside/concern/blocker 判定与阻断追踪。
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.advisor_channel import (
    DualModelAdvisorEngine,
    get_default_advisor_engine,
)

from app.schemas.advisor_channel import (
    AdvisorInterventionDTO,
    AdvisorReviewResultDTO,
    AdvisorReviewStepRequestDTO,
    AdvisorSessionReviewsResponseDTO,
)


class AdvisorChannelService:
    """会话级双模型实时旁路审查管理业务服务。"""

    def __init__(self, engine: DualModelAdvisorEngine | None = None) -> None:
        self._engine = engine or get_default_advisor_engine()
        # session_id -> 历史干预记录列表
        self._history_store: dict[str, list[AdvisorInterventionDTO]] = {}
        # session_id -> 总审查次数
        self._review_counts: dict[str, int] = {}

    def review_step(self, request: AdvisorReviewStepRequestDTO) -> AdvisorReviewResultDTO:
        """
        对主 Agent 的单步 Tool Call 与计划意图执行非侵入旁路审查。
        归档生成的干预建议，若命中 blocker 则产生硬性熔断标记。
        """
        session_id = request.session_id
        self._review_counts[session_id] = self._review_counts.get(session_id, 0) + 1

        domain_result = self._engine.review_step(
            task_goal=request.task_goal,
            tool_name=request.tool_name,
            tool_args=request.tool_args,
            turn_index=request.turn_index,
        )

        intervention_dtos: list[AdvisorInterventionDTO] = [
            AdvisorInterventionDTO(
                intervention_id=it.intervention_id,
                level=it.level,
                title=it.title,
                message=it.message,
                suggested_action=it.suggested_action,
                created_at=it.created_at,
                duration_ms=it.duration_ms,
                tokens_used=it.tokens_used,
            )
            for it in domain_result.interventions
        ]

        # 归档到会话历史中
        if intervention_dtos:
            session_history = self._history_store.setdefault(session_id, [])
            session_history.extend(intervention_dtos)

        return AdvisorReviewResultDTO(
            is_blocked=domain_result.is_blocked,
            highest_level=domain_result.highest_level,
            interventions=intervention_dtos,
            summary=domain_result.summary,
        )

    def get_session_reviews(self, session_id: str) -> AdvisorSessionReviewsResponseDTO:
        """获取指定会话的历史旁路审查干预汇总。"""
        interventions = self._history_store.get(session_id, [])
        total_reviews = self._review_counts.get(session_id, len(interventions))
        blocked_count = sum(1 for it in interventions if it.level == "blocker")

        return AdvisorSessionReviewsResponseDTO(
            session_id=session_id,
            total_reviews=total_reviews,
            blocked_count=blocked_count,
            interventions=list(interventions),
        )

    def clear_session_reviews(self, session_id: str) -> None:
        """清理指定会话的审查记录。"""
        self._history_store.pop(session_id, None)
        self._review_counts.pop(session_id, None)


_GLOBAL_ADVISOR_SERVICE: AdvisorChannelService | None = None


def get_advisor_channel_service() -> AdvisorChannelService:
    """获取单例 AdvisorChannelService 实例。"""
    global _GLOBAL_ADVISOR_SERVICE
    if _GLOBAL_ADVISOR_SERVICE is None:
        _GLOBAL_ADVISOR_SERVICE = AdvisorChannelService()
    return _GLOBAL_ADVISOR_SERVICE
