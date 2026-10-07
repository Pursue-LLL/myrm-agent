"""
[POS] app/services/project/project_state_service.py
[INPUT] myrm_agent_harness.agent.context_management.project_state, app.schemas.project_state
[OUTPUT] ProjectStateService, get_project_state_service

Service layer bridge connecting server runtime to Harness ProjectStateLivingFactLedger and FourTierContextProjectionEngine.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from typing import cast

from myrm_agent_harness.agent.context_management.project_state import (
    FactPromotionStage,
    FourTierContextProjectionEngine,
    LivingFact,
    ProjectFactType,
    ProjectionQuery,
    ProjectStateLivingFactLedger,
    ValidationAuditInput,
    ValidationGatedPromotionGate,
)

from app.schemas.project_state import (
    ContextProjectionRequestDTO,
    ContextProjectionResponseDTO,
    CreateLivingFactRequestDTO,
    LivingFactDTO,
    LivingFactListResponseDTO,
    ValidationAuditRequestDTO,
    ValidationAuditResponseDTO,
)


class ProjectStateService:
    """长期项目动态事实状态账本与四层级联上下文投影业务服务。"""

    def __init__(
        self, ledger: ProjectStateLivingFactLedger | None = None
    ) -> None:
        self._ledger = ledger or ProjectStateLivingFactLedger()
        self._projection_engine = FourTierContextProjectionEngine(self._ledger)
        self._validation_gate = ValidationGatedPromotionGate(self._ledger)

    @staticmethod
    def _to_dto(fact: LivingFact) -> LivingFactDTO:
        """将 Harness LivingFact 领域实体转换为 DTO。"""
        return LivingFactDTO(
            fact_id=fact.fact_id,
            project_id=fact.project_id,
            fact_type=fact.fact_type.value,
            title=fact.title,
            content=fact.content,
            target_components=list(fact.target_components),
            reason_or_constraint=fact.reason_or_constraint,
            validation_count=fact.validation_count,
            regression_count=fact.regression_count,
            promotion_stage=fact.promotion_stage.value,
            created_at=fact.created_at,
            updated_at=fact.updated_at,
            metadata=dict(fact.metadata),
        )

    def record_fact(
        self, project_id: str, req: CreateLivingFactRequestDTO
    ) -> LivingFactDTO:
        """登记或更新长期项目事实项。"""
        fact_type_val = req.fact_type.lower()
        matched_type = ProjectFactType.CONFIRMED_FACT if hasattr(ProjectFactType, "CONFIRMED_FACT") else ProjectFactType.DECISION
        for ft in ProjectFactType:
            if ft.value == fact_type_val:
                matched_type = ft
                break

        stage_val = req.promotion_stage.lower()
        matched_stage = FactPromotionStage.CONFIRMED_FACT
        for st in FactPromotionStage:
            if st.value == stage_val:
                matched_stage = st
                break

        fact = self._ledger.create_fact(
            project_id=project_id,
            fact_id=req.fact_id,
            fact_type=matched_type,
            title=req.title,
            content=req.content,
            target_components=req.target_components,
            reason_or_constraint=req.reason_or_constraint,
            stage=matched_stage,
            metadata=req.metadata,
        )
        return self._to_dto(fact)

    def get_fact(self, project_id: str, fact_id: str) -> LivingFactDTO | None:
        """检索项目下的指定事实项。"""
        fact = self._ledger.get_fact(project_id, fact_id)
        if not fact:
            return None
        return self._to_dto(fact)

    def list_facts(
        self,
        project_id: str,
        fact_type: str | None = None,
        stage: str | None = None,
    ) -> LivingFactListResponseDTO:
        """查询指定项目下的全部事实项，支持类型和晋升阶梯过滤。"""
        filter_type: ProjectFactType | None = None
        if fact_type:
            for ft in ProjectFactType:
                if ft.value == fact_type.lower():
                    filter_type = ft
                    break

        filter_stage: FactPromotionStage | None = None
        if stage:
            for st in FactPromotionStage:
                if st.value == stage.lower():
                    filter_stage = st
                    break

        domain_facts = self._ledger.list_facts(
            project_id=project_id,
            fact_type=filter_type,
            stage=filter_stage,
        )
        dtos = [self._to_dto(f) for f in domain_facts]
        return LivingFactListResponseDTO(
            project_id=project_id,
            total_count=len(dtos),
            facts=dtos,
        )

    def delete_fact(self, project_id: str, fact_id: str) -> bool:
        """从项目事实账本中移除指定条目。"""
        return self._ledger.remove_fact(project_id, fact_id)

    def project_context(
        self, project_id: str, req: ContextProjectionRequestDTO
    ) -> ContextProjectionResponseDTO:
        """执行四层级联动态上下文投影流水线，萃取最小高密度上下文切片。"""
        query = ProjectionQuery(
            project_id=project_id,
            target_task=req.target_task,
            target_components=req.target_components,
            token_budget=req.token_budget,
        )
        slice_result = self._projection_engine.project_context(query)
        dtos = [self._to_dto(f) for f in slice_result.facts]

        return ContextProjectionResponseDTO(
            project_id=project_id,
            formatted_prompt_block=slice_result.formatted_prompt_block,
            total_tokens_estimated=slice_result.total_tokens_estimated,
            facts=dtos,
            projected_by_tier=cast(dict[str, int], slice_result.projected_by_tier),
        )

    def audit_validation(
        self, project_id: str, req: ValidationAuditRequestDTO
    ) -> ValidationAuditResponseDTO:
        """审计确定性验证结果，触发事实生命周期状态晋升与经验沉淀。"""
        audit_input = ValidationAuditInput(
            project_id=project_id,
            fact_id=req.fact_id,
            passed=req.passed,
            test_summary=req.test_summary,
        )
        audit_res = self._validation_gate.audit_validation(audit_input)

        return ValidationAuditResponseDTO(
            fact_id=audit_res.fact_id,
            new_stage=audit_res.new_stage.value,
            validation_count=audit_res.validation_count,
            regression_count=audit_res.regression_count,
            is_promoted=audit_res.is_promoted,
            recommend_skill_extraction=audit_res.recommend_skill_extraction,
            message=audit_res.message,
        )


_service_instance: ProjectStateService | None = None


def get_project_state_service() -> ProjectStateService:
    """获取 ProjectStateService 单例实例。"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ProjectStateService()
    return _service_instance
