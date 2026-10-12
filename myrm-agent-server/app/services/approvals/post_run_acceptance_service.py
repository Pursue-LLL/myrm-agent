"""Post-run deterministic deliverable acceptance service.

[INPUT]
- AcceptanceEvaluationRequest from app.schemas.side_effect_gate
- DeterministicAcceptanceEvaluator from myrm_agent_harness.core.security.side_effect_gate

[OUTPUT]
- PostRunAcceptanceService: Runs deterministic quality gate on agent deliverables
- get_post_run_acceptance_service: Singleton dependency provider

[POS]
Server service. Decouples task completion from acceptance by executing deterministic
rule checks before marking deliverables approved or completed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.side_effect_gate import (
    AcceptanceReport,
    AcceptanceRule,
    AcceptanceRuleType,
    DeterministicAcceptanceEvaluator,
)

from app.schemas.side_effect_gate import (
    AcceptanceEvaluationRequest,
    AcceptanceEvaluationResponse,
    AcceptanceRuleDto,
    AcceptanceViolationDto,
)

logger = logging.getLogger(__name__)


def _dto_to_rule(dto: AcceptanceRuleDto) -> AcceptanceRule:
    return AcceptanceRule(
        rule_type=AcceptanceRuleType(dto.rule_type),
        description=dto.description,
        min_length=dto.min_length,
        max_length=dto.max_length,
        required_sections=dto.required_sections,
        required_json_keys=dto.required_json_keys,
        sum_field_names=dto.sum_field_names,
        total_field_name=dto.total_field_name,
    )


class PostRunAcceptanceService:
    """Executes deterministic post-run quality checks on agent deliverables."""

    def __init__(self, evaluator: DeterministicAcceptanceEvaluator | None = None) -> None:
        self._evaluator = evaluator if evaluator is not None else DeterministicAcceptanceEvaluator()

    def evaluate(self, request: AcceptanceEvaluationRequest) -> AcceptanceEvaluationResponse:
        """Evaluate text or structured deliverables against deterministic rules."""
        rules = [_dto_to_rule(r) for r in request.rules]

        if request.text_content is not None:
            report: AcceptanceReport = self._evaluator.evaluate_text(request.text_content, rules)
        elif request.structured_payload is not None:
            report = self._evaluator.evaluate_structured(request.structured_payload, rules)
        else:
            return AcceptanceEvaluationResponse(
                passed=False,
                summary="Neither text_content nor structured_payload was provided for evaluation",
                violations=[
                    AcceptanceViolationDto(
                        rule_type="input_validation",
                        message="Missing deliverable payload for acceptance gate",
                        actual_value=None,
                    )
                ],
                evaluated_at=0.0,
            )

        violations_dto = [
            AcceptanceViolationDto(
                rule_type=v.rule_type.value,
                message=v.message,
                actual_value=v.actual_value,
            )
            for v in report.violations
        ]

        logger.info(
            "Deterministic acceptance evaluated: passed=%s, violations_count=%d",
            report.passed,
            len(report.violations),
        )

        return AcceptanceEvaluationResponse(
            passed=report.passed,
            summary=report.summary,
            violations=violations_dto,
            evaluated_at=report.evaluated_at,
        )


_global_post_run_acceptance_service: PostRunAcceptanceService | None = None


def get_post_run_acceptance_service() -> PostRunAcceptanceService:
    """Singleton getter for PostRunAcceptanceService."""
    global _global_post_run_acceptance_service
    if _global_post_run_acceptance_service is None:
        _global_post_run_acceptance_service = PostRunAcceptanceService()
    return _global_post_run_acceptance_service
