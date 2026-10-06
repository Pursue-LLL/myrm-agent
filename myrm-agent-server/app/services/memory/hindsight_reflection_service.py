"""
[POS] app/services/memory/hindsight_reflection_service.py
[INPUT] app/schemas/hindsight_reflection.py, myrm_agent_harness.toolkits.memory.strategies.hindsight
[OUTPUT] HindsightReflectionService, get_hindsight_reflection_service
"""

from __future__ import annotations

import time

from myrm_agent_harness.toolkits.memory.strategies.hindsight import (
    CounterfactualRuleExtractor,
    FailureTrajectoryScrubber,
    FailureTurn,
    HindsightReflectionBuffer,
    HindsightRule,
    PreExecutionWarning,
    ReflectionBufferConfig,
)

from app.schemas.hindsight_reflection import (
    HindsightRuleResponse,
    PreExecutionWarningQuery,
    PreExecutionWarningResponse,
    PreExecutionWarningsListResponse,
    ReflectionBufferStatsResponse,
    ReflectTaskFailureRequest,
    ReflectTaskFailureResponse,
)


class HindsightReflectionService:
    """Service orchestrating failure trajectory scrubbing, counterfactual learning, and warning delivery."""

    def __init__(self, config: ReflectionBufferConfig | None = None) -> None:
        self.scrubber = FailureTrajectoryScrubber()
        self.extractor = CounterfactualRuleExtractor()
        self.buffer = HindsightReflectionBuffer(config=config)

    def reflect_and_record(
        self, req: ReflectTaskFailureRequest
    ) -> ReflectTaskFailureResponse:
        """Clean trajectory, extract counterfactual rule, and register into the buffer."""
        raw_turns = [
            FailureTurn(
                turn_index=t.turn_index,
                tool_name=t.tool_name,
                tool_input=dict(t.tool_input),
                tool_output=t.tool_output,
                error_message=t.error_message,
                timestamp=t.timestamp or time.time(),
            )
            for t in req.trajectory.turns
        ]

        cleaned_traj = self.scrubber.scrub(
            task_id=req.trajectory.task_id,
            task_goal=req.trajectory.task_goal,
            turns=raw_turns,
            terminal_error=req.trajectory.terminal_error,
            max_turns=req.max_turns,
        )

        turning_point = self.scrubber.locate_turning_point(cleaned_traj)
        extracted_rule = self.extractor.extract_rule(
            trajectory=cleaned_traj, turning_point=turning_point
        )
        saved_rule: HindsightRule = self.buffer.record_rule(extracted_rule)

        rule_resp = HindsightRuleResponse(
            rule_id=saved_rule.rule_id,
            task_pattern=saved_rule.task_pattern,
            mistake_signature=saved_rule.mistake_signature,
            correction_advice=saved_rule.correction_advice,
            tags=saved_rule.tags,
            confidence=saved_rule.confidence,
            hit_count=saved_rule.hit_count,
            created_at=saved_rule.created_at,
        )

        return ReflectTaskFailureResponse(
            rule=rule_resp,
            status="success",
            message="Hindsight reflection extracted and registered",
        )

    def get_warnings(
        self, req: PreExecutionWarningQuery
    ) -> PreExecutionWarningsListResponse:
        """Retrieve cautionary guardrail directives tailored to the upcoming task goal."""
        warnings: list[PreExecutionWarning] = self.buffer.match_warnings(
            task_goal=req.task_goal,
            intended_tools=req.intended_tools,
            top_k=req.top_k,
        )

        resp_items = [
            PreExecutionWarningResponse(
                rule_id=w.rule_id,
                task_pattern=w.task_pattern,
                warning_text=w.warning_text,
                recommended_action=w.recommended_action,
                confidence=w.confidence,
            )
            for w in warnings
        ]

        return PreExecutionWarningsListResponse(
            warnings=resp_items,
            total_warnings=len(resp_items),
            task_goal=req.task_goal,
        )

    def get_rules(self) -> list[HindsightRuleResponse]:
        """Fetch all currently registered hindsight rules."""
        rules = self.buffer.get_all_rules()
        return [
            HindsightRuleResponse(
                rule_id=r.rule_id,
                task_pattern=r.task_pattern,
                mistake_signature=r.mistake_signature,
                correction_advice=r.correction_advice,
                tags=r.tags,
                confidence=r.confidence,
                hit_count=r.hit_count,
                created_at=r.created_at,
            )
            for r in rules
        ]

    def get_stats(self) -> ReflectionBufferStatsResponse:
        """Fetch operational statistics of the buffer."""
        stats = self.buffer.get_stats()
        return ReflectionBufferStatsResponse(
            total_rules=int(stats["total_rules"]),
            avg_confidence=float(stats["avg_confidence"]),
            total_hits=int(stats["total_hits"]),
        )


_default_service: HindsightReflectionService | None = None


def get_hindsight_reflection_service() -> HindsightReflectionService:
    """Return default singleton instance of HindsightReflectionService."""
    global _default_service
    if _default_service is None:
        _default_service = HindsightReflectionService()
    return _default_service
