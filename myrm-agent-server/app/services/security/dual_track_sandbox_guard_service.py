"""Service layer for Dual-Track Soft Memory vs Hard Redline Sandbox Guard.

[INPUT]
- EvaluateExecutionRequest, RegisterRedlineRuleRequest DTOs.

[OUTPUT]
- ExecutionInterceptionDto, HardRedlineRuleDto, CompiledPolicySummaryDto.

[POS]
- Server service wrapping harness RedlinePolicyCompiler and DualTrackSandboxGuard.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.dual_track_sandbox_guard.guard_interceptor import (
    DualTrackSandboxGuard,
)
from myrm_agent_harness.core.security.dual_track_sandbox_guard.policy_compiler import (
    RedlinePolicyCompiler,
)
from myrm_agent_harness.core.security.dual_track_sandbox_guard.types import (
    HardRedlineRule,
    RedlineCategory,
)

from app.schemas.dual_track_sandbox_guard import (
    CompiledPolicySummaryDto,
    EvaluateExecutionRequest,
    ExecutionInterceptionDto,
    HardRedlineRuleDto,
    RegisterRedlineRuleRequest,
)


class DualTrackSandboxGuardService:
    """Coordinates policy compilation and pre-execution physical sandbox firewall gating."""

    def __init__(
        self,
        compiler: RedlinePolicyCompiler | None = None,
        guard: DualTrackSandboxGuard | None = None,
    ) -> None:
        self._compiler = compiler or RedlinePolicyCompiler()
        self._guard = guard or DualTrackSandboxGuard(self._compiler)

    def evaluate_execution(
        self, request: EvaluateExecutionRequest
    ) -> ExecutionInterceptionDto:
        """Evaluate an operation candidate against the physical sandbox execution firewall."""
        if request.operation_type.lower() == "file":
            verdict = self._guard.evaluate_file_access(
                file_path=request.target,
                operation=request.sub_operation,
            )
        else:
            verdict = self._guard.evaluate_command_execution(command=request.target)

        return ExecutionInterceptionDto(
            verdict=verdict.verdict.value,
            is_permitted=verdict.is_permitted,
            blocked_by_rule_id=verdict.blocked_by_rule_id,
            target_operation=verdict.target_operation,
            audit_id=verdict.audit_id,
            rationale=verdict.rationale,
        )

    def register_rule(
        self, request: RegisterRedlineRuleRequest
    ) -> HardRedlineRuleDto:
        """Add a custom hard redline rule to the policy compiler."""
        category_enum = RedlineCategory(request.category)
        rule = HardRedlineRule(
            rule_id=request.rule_id,
            category=category_enum,
            pattern=request.pattern,
            description=request.description,
            severity=request.severity,
            is_immutable=True,
        )
        self._compiler.register_rule(rule)

        return HardRedlineRuleDto(
            rule_id=rule.rule_id,
            category=rule.category.value,
            pattern=rule.pattern,
            description=rule.description,
            severity=rule.severity,
            is_immutable=rule.is_immutable,
        )

    def get_compiled_policy(self) -> CompiledPolicySummaryDto:
        """Compile and summarize active sandbox physical execution rules."""
        policy = self._compiler.compile()
        return CompiledPolicySummaryDto(
            rule_count=policy.rule_count,
            blocked_file_patterns=list(policy.blocked_file_patterns),
            blocked_command_regexes=list(policy.blocked_command_regexes),
            enforced_at=policy.enforced_at,
        )

    def list_rules(self) -> list[HardRedlineRuleDto]:
        """List all active hard redline rules."""
        return [
            HardRedlineRuleDto(
                rule_id=r.rule_id,
                category=r.category.value,
                pattern=r.pattern,
                description=r.description,
                severity=r.severity,
                is_immutable=r.is_immutable,
            )
            for r in self._compiler.get_all_rules()
        ]


_default_service: DualTrackSandboxGuardService | None = None


def get_dual_track_sandbox_guard_service() -> DualTrackSandboxGuardService:
    """Singleton provider for DualTrackSandboxGuardService."""
    global _default_service
    if _default_service is None:
        _default_service = DualTrackSandboxGuardService()
    return _default_service
