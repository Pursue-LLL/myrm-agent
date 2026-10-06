"""
[POS] app/services/security/decoupled_watchdog_service.py
[INPUT] app/schemas/decoupled_watchdog.py, myrm_agent_harness.core.security.decoupled_watchdog
[OUTPUT] DecoupledWatchdogService, get_decoupled_watchdog_service

Service layer for decoupled action watchdog and inbound multimodal content firewall suite.

Orchestrates input sanitization and decoupled action arbitration, tracks telemetry,
and enforces safety invariants.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.decoupled_watchdog import (
    ActionContractSpec,
    DecoupledActionWatchdogSuite,
    InvarianceAssertionRule,
    WatchdogVerdictStatus,
)

from app.schemas.decoupled_watchdog import (
    FirewallSanitizeRequest,
    FirewallSanitizeResponse,
    InvarianceAssertionRuleSchema,
    ThreatSeverityEnum,
    WatchdogInspectRequest,
    WatchdogInspectResponse,
    WatchdogMetricsResponse,
    WatchdogVerdictStatusEnum,
    WatchdogViolationDetailSchema,
)


class DecoupledWatchdogService:
    """Manages input content firewalling and decoupled action watchdog arbitration."""

    def __init__(self) -> None:
        self._suite = DecoupledActionWatchdogSuite()
        self._rules: dict[str, InvarianceAssertionRule] = {}
        self._lock = threading.Lock()

        # Telemetry metrics
        self._total_inspected_actions: int = 0
        self._approved_actions: int = 0
        self._blocked_actions: int = 0
        self._circuit_breaker_trips: int = 0
        self._confirmation_required_count: int = 0
        self._total_sanitized_inputs: int = 0
        self._total_inspection_latency_ms: float = 0.0

    def sanitize_inbound_content(self, request: FirewallSanitizeRequest) -> FirewallSanitizeResponse:
        """Sanitize inbound multimodal content via the firewall."""
        res = self._suite.sanitize_inbound_content(
            raw_content=request.raw_content,
            source_type=request.source_type,
        )
        with self._lock:
            self._total_sanitized_inputs += 1

        return FirewallSanitizeResponse(
            source_type=res.source_type,
            sanitized_content=res.sanitized_content,
            hidden_text_stripped_count=res.hidden_text_stripped_count,
            has_markdown_injection=res.has_markdown_injection,
            stripped_tags=res.stripped_tags,
            latency_ms=res.latency_ms,
        )

    def inspect_action(self, request: WatchdogInspectRequest) -> WatchdogInspectResponse:
        """Inspect a proposed action contract through the decoupled watchdog."""
        # Convert schema spec to harness spec
        harness_spec = ActionContractSpec(
            action_id=request.action.action_id,
            tool_name=request.action.tool_name,
            arguments=request.action.arguments,
            user_original_intent=request.action.user_original_intent,
            caller_role=request.action.caller_role,
            snapshot_context=request.action.snapshot_context,
        )

        # Resolve rule
        harness_rule: Optional[InvarianceAssertionRule] = None
        if request.rule is not None:
            harness_rule = InvarianceAssertionRule(
                rule_name=request.rule.rule_name,
                target_tool=request.rule.target_tool,
                max_amount_limit=request.rule.max_amount_limit,
                allowed_recipients=tuple(request.rule.allowed_recipients),
                prohibited_destinations=tuple(request.rule.prohibited_destinations),
                strict_intent_binding=request.rule.strict_intent_binding,
            )
        elif request.action.tool_name in self._rules:
            with self._lock:
                harness_rule = self._rules.get(request.action.tool_name)

        result = self._suite.inspect_proposed_action(spec=harness_spec, rule=harness_rule)

        # Map enum
        status_map: dict[str, WatchdogVerdictStatusEnum] = {
            WatchdogVerdictStatus.APPROVED.value: WatchdogVerdictStatusEnum.APPROVED,
            WatchdogVerdictStatus.BLOCKED.value: WatchdogVerdictStatusEnum.BLOCKED,
            WatchdogVerdictStatus.CIRCUIT_BREAKER_TRIGGERED.value: WatchdogVerdictStatusEnum.CIRCUIT_BREAKER_TRIGGERED,
            WatchdogVerdictStatus.NEEDS_CONFIRMATION.value: WatchdogVerdictStatusEnum.NEEDS_CONFIRMATION,
        }
        verdict_enum = status_map.get(result.verdict.value, WatchdogVerdictStatusEnum.BLOCKED)

        violations_schemas = [
            WatchdogViolationDetailSchema(
                violation_type=v.violation_type,
                threat_severity=ThreatSeverityEnum(v.threat_severity.value),
                description=v.description,
                parameter_key=v.parameter_key,
                observed_value=v.observed_value,
                expected_constraint=v.expected_constraint,
            )
            for v in result.violations
        ]

        with self._lock:
            self._total_inspected_actions += 1
            self._total_inspection_latency_ms += result.latency_ms
            if verdict_enum == WatchdogVerdictStatusEnum.APPROVED:
                self._approved_actions += 1
            elif verdict_enum == WatchdogVerdictStatusEnum.CIRCUIT_BREAKER_TRIGGERED:
                self._circuit_breaker_trips += 1
                self._blocked_actions += 1
            elif verdict_enum == WatchdogVerdictStatusEnum.NEEDS_CONFIRMATION:
                self._confirmation_required_count += 1
            else:
                self._blocked_actions += 1

        return WatchdogInspectResponse(
            action_id=result.action_id,
            verdict=verdict_enum,
            confidence_score=result.confidence_score,
            violations=violations_schemas,
            circuit_breaker_active=result.circuit_breaker_active,
            latency_ms=result.latency_ms,
            rationale=result.rationale,
        )

    def register_rule(self, rule_schema: InvarianceAssertionRuleSchema) -> None:
        """Register or update an invariance assertion rule for a tool."""
        with self._lock:
            self._rules[rule_schema.target_tool] = InvarianceAssertionRule(
                rule_name=rule_schema.rule_name,
                target_tool=rule_schema.target_tool,
                max_amount_limit=rule_schema.max_amount_limit,
                allowed_recipients=tuple(rule_schema.allowed_recipients),
                prohibited_destinations=tuple(rule_schema.prohibited_destinations),
                strict_intent_binding=rule_schema.strict_intent_binding,
            )

    def get_metrics(self) -> WatchdogMetricsResponse:
        """Retrieve aggregated security metrics."""
        with self._lock:
            avg_lat = (
                (self._total_inspection_latency_ms / self._total_inspected_actions)
                if self._total_inspected_actions > 0
                else 0.0
            )
            return WatchdogMetricsResponse(
                total_inspected_actions=self._total_inspected_actions,
                approved_actions=self._approved_actions,
                blocked_actions=self._blocked_actions,
                circuit_breaker_trips=self._circuit_breaker_trips,
                confirmation_required_count=self._confirmation_required_count,
                total_sanitized_inputs=self._total_sanitized_inputs,
                avg_latency_ms=round(avg_lat, 3),
            )


_global_service: Optional[DecoupledWatchdogService] = None
_global_lock = threading.Lock()


def get_decoupled_watchdog_service() -> DecoupledWatchdogService:
    """Get the singleton instance of DecoupledWatchdogService."""
    global _global_service
    if _global_service is None:
        with _global_lock:
            if _global_service is None:
                _global_service = DecoupledWatchdogService()
    return _global_service
