"""
[INPUT]
- typing (Optional)
- myrm_agent_harness.agent.sub_agents.ralph_loop (
    RalphFreshAgentLoopCoordinator,
    RalphHandoffReport,
    RalphLoopConfig,
    RalphLoopSession,
    get_ralph_loop_coordinator,
  )
- app.schemas.ralph_workflow (
    AdvanceRalphRoundRequestDTO,
    CreateRalphSessionRequestDTO,
    RalphHandoffReportDTO,
    RalphRoundRecordDTO,
    RalphSessionResponseDTO,
  )

[OUTPUT]
- RalphWorkflowService: Ralph 式 Fresh-Agent 多轮循环管理业务服务
- get_ralph_workflow_service: 获取单例服务的工厂函数

[POS]
Server 业务层 Ralph 式 Fresh-Agent 多轮循环服务（Topic 12 · 第 15 项）。
将 Harness 框架层 RalphFreshAgentLoopCoordinator 包装为业务服务，驱动零会话 seed 的满血多轮迭代。
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.ralph_loop import (
    RalphFreshAgentLoopCoordinator,
    RalphHandoffReport,
    RalphLoopConfig,
    RalphLoopSession,
    get_ralph_loop_coordinator,
)

from app.schemas.ralph_workflow import (
    AdvanceRalphRoundRequestDTO,
    CreateRalphSessionRequestDTO,
    RalphHandoffReportDTO,
    RalphRoundRecordDTO,
    RalphSessionResponseDTO,
)


class RalphWorkflowService:
    """Ralph 式 Fresh-Agent 多轮循环业务管理服务。"""

    def __init__(self, coordinator: RalphFreshAgentLoopCoordinator | None = None) -> None:
        self._coordinator = coordinator or get_ralph_loop_coordinator()

    def create_session(self, request: CreateRalphSessionRequestDTO) -> RalphSessionResponseDTO:
        """创建全新 Ralph 多轮循环会话。"""
        config = RalphLoopConfig(
            max_rounds=request.max_rounds,
            min_rounds_before_blocked=request.min_rounds_before_blocked,
        )
        session = self._coordinator.create_session(
            human_goal=request.human_goal,
            workspace_root=request.workspace_root,
            config=config,
        )
        return self._to_response_dto(session)

    def get_session(self, session_id: str) -> RalphSessionResponseDTO | None:
        """获取指定 Ralph 循环会话状态。"""
        session = self._coordinator.get_session(session_id)
        if session is None:
            return None
        return self._to_response_dto(session)

    def advance_round(
        self,
        session_id: str,
        request: AdvanceRalphRoundRequestDTO,
    ) -> RalphSessionResponseDTO:
        """归档本轮执行结果并推进至下一轮 Fresh 子 Agent 启动状态。"""
        handoff_domain = RalphHandoffReport(
            status=request.handoff.status,
            summary=request.handoff.summary,
            evidence=request.handoff.evidence,
            next_steps=request.handoff.next_steps,
            blocker=request.handoff.blocker,
        )

        self._coordinator.record_round_completion(
            session_id=session_id,
            child_session_id=request.child_session_id,
            raw_handoff=handoff_domain,
            duration_seconds=request.duration_seconds,
            tokens_consumed=request.tokens_consumed,
        )

        session = self._coordinator.get_session(session_id)
        if session is None:
            raise KeyError(f"Ralph session not found: {session_id}")

        return self._to_response_dto(session)

    def _to_response_dto(self, session: RalphLoopSession) -> RalphSessionResponseDTO:
        """将 Harness 领域模型装配为 API 响应 DTO。"""
        round_dtos: list[RalphRoundRecordDTO] = [
            RalphRoundRecordDTO(
                round_index=rec.round_index,
                child_session_id=rec.child_session_id,
                handoff=RalphHandoffReportDTO(
                    status=rec.handoff.status,
                    summary=rec.handoff.summary,
                    evidence=rec.handoff.evidence,
                    next_steps=rec.handoff.next_steps,
                    blocker=rec.handoff.blocker,
                ),
                created_at=rec.created_at,
                duration_seconds=rec.duration_seconds,
                tokens_consumed=rec.tokens_consumed,
                was_blocked_downgraded=rec.was_blocked_downgraded,
            )
            for rec in session.rounds
        ]

        next_directive: str | None = None
        if session.status == "in_progress":
            try:
                next_directive = self._coordinator.generate_next_round_directive(session.session_id)
            except Exception:
                next_directive = None

        return RalphSessionResponseDTO(
            session_id=session.session_id,
            human_goal=session.human_goal,
            workspace_root=session.workspace_root,
            current_round=session.current_round,
            max_rounds=session.config.max_rounds,
            min_rounds_before_blocked=session.config.min_rounds_before_blocked,
            status=session.status,
            rounds=round_dtos,
            next_directive=next_directive,
        )


_GLOBAL_SERVICE: RalphWorkflowService | None = None


def get_ralph_workflow_service() -> RalphWorkflowService:
    """获取单例 RalphWorkflowService 实例。"""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = RalphWorkflowService()
    return _GLOBAL_SERVICE
