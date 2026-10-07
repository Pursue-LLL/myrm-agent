# [POS]: app/services/memory/business_template_service.py
# [INPUT]: app.schemas.business_templates, myrm_agent_harness.toolkits.memory.business_templates
# [OUTPUT]: BusinessTemplateService, get_business_template_service

from __future__ import annotations

import logging
from functools import lru_cache
from typing import cast

from myrm_agent_harness.toolkits.memory import (
    BusinessExperienceTemplate,
    BusinessTemplateEngine,
    EscalationEvaluationContext,
    ProcedureMemoryEntry,
    TemplateCategory,
)

from app.schemas.business_templates import (
    BusinessExperienceTemplateDTO,
    ChecklistStepDTO,
    EscalationEvaluationRequest,
    EscalationEvaluationResponseDTO,
    ExportProcedureMemoriesResponseDTO,
    ExportProcedureMemoryItem,
    ListTemplatesResponseDTO,
    RecordValidationRequest,
    RecordValidationResponseDTO,
)

logger = logging.getLogger(__name__)


def _template_to_dto(tpl: BusinessExperienceTemplate) -> BusinessExperienceTemplateDTO:
    """Map internal domain model to DTO schema."""
    return BusinessExperienceTemplateDTO(
        template_id=tpl.template_id,
        name=tpl.name,
        category=tpl.category.value,
        summary=tpl.summary,
        checklist_steps=[
            ChecklistStepDTO(
                step_index=s.step_index,
                name=s.name,
                description=s.description,
                mandatory=s.mandatory,
                validation_rule=s.validation_rule,
            )
            for s in tpl.checklist_steps
        ],
        boundary_conditions=list(tpl.boundary_conditions),
        sample_trajectory_ref=tpl.sample_trajectory_ref,
        version=tpl.version,
        tags=list(tpl.tags),
        metadata=dict(tpl.metadata),
        validated_count=tpl.validated_count,
        rejected_count=tpl.rejected_count,
        last_validated_at=tpl.last_validated_at,
    )


class BusinessTemplateService:
    """Application service providing business experience templates and escalation evaluations."""

    def __init__(self, engine: BusinessTemplateEngine | None = None) -> None:
        self._engine = engine if engine is not None else BusinessTemplateEngine()

    def list_templates(
        self,
        category_str: str | None = None,
        query: str | None = None,
    ) -> ListTemplatesResponseDTO:
        """List templates matching optional category and query."""
        if query:
            raw_list = self._engine.search_templates(query)
            if category_str:
                raw_list = [t for t in raw_list if t.category.value == category_str]
        elif category_str:
            try:
                cat = TemplateCategory(category_str)
                raw_list = self._engine.list_templates(category=cat)
            except ValueError:
                raw_list = []
        else:
            raw_list = self._engine.list_templates()

        dtos = [_template_to_dto(t) for t in raw_list]
        return ListTemplatesResponseDTO(
            status="ok",
            total_count=len(dtos),
            templates=dtos,
        )

    def get_template(self, template_id: str) -> BusinessExperienceTemplateDTO | None:
        """Retrieve a specific template by ID."""
        tpl = self._engine.get_template(template_id)
        if tpl is None:
            return None
        return _template_to_dto(tpl)

    def evaluate_escalation(
        self,
        req: EscalationEvaluationRequest,
    ) -> EscalationEvaluationResponseDTO:
        """Evaluate customer context against human escalation boundary gates."""
        ctx = EscalationEvaluationContext(
            order_id=req.order_id,
            user_id=req.user_id,
            intent=req.intent,
            shipment_status=req.shipment_status,
            warranty_valid=req.warranty_valid,
            inventory_available=req.inventory_available,
            user_dispute_count=req.user_dispute_count,
            is_custom_order=req.is_custom_order,
            policy_clear=req.policy_clear,
            user_confirmed=req.user_confirmed,
        )
        decision = self._engine.evaluate_escalation(ctx)
        return EscalationEvaluationResponseDTO(
            action=decision.action.value,
            reason=decision.reason.value,
            message=decision.message,
            required_context=decision.required_context,
            suggested_skill_or_tool=decision.suggested_skill_or_tool,
        )

    def record_validation(
        self,
        req: RecordValidationRequest,
    ) -> RecordValidationResponseDTO | None:
        """Record validation feedback to update template confidence metrics."""
        rec = self._engine.record_validation(
            template_id=req.template_id,
            is_validated=req.is_validated,
            note=req.note,
        )
        if rec is None:
            return None

        tpl = self._engine.get_template(req.template_id)
        val_count = tpl.validated_count if tpl else 0
        rej_count = tpl.rejected_count if tpl else 0

        return RecordValidationResponseDTO(
            status="ok",
            record_id=rec.record_id,
            template_id=rec.template_id,
            is_validated=rec.is_validated,
            validated_count=val_count,
            rejected_count=rej_count,
            timestamp=rec.timestamp,
        )

    def export_procedure_memories(self) -> ExportProcedureMemoriesResponseDTO:
        """Export all registered templates as standard procedure memory items."""
        raw_entries = self._engine.export_as_procedure_memories()
        entries = cast(list[ProcedureMemoryEntry], raw_entries)
        items = [
            ExportProcedureMemoryItem(
                entry_id=e.entry_id,
                name=e.name,
                retrieval_anchor=e.retrieval_anchor,
                operation_intent=e.operation_intent,
                preconditions=list(e.preconditions),
                immutable_boundary=list(e.immutable_boundary),
                procedure_steps=list(e.procedure_steps),
                confidence=e.confidence,
            )
            for e in entries
        ]
        return ExportProcedureMemoriesResponseDTO(
            status="ok",
            total_count=len(items),
            items=items,
        )


@lru_cache(maxsize=1)
def get_business_template_service() -> BusinessTemplateService:
    """Obtain singleton instance of BusinessTemplateService."""
    return BusinessTemplateService()
