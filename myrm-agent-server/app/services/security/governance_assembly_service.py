"""Governance Assembly Path Assertion & Zero-Bypass Service.

[INPUT]
- RecordInvocationRequest, VerifyToolGovernanceRequest, SimulateWorkflowRequest.

[OUTPUT]
- ToolCallAssemblyTraceDto, GovernanceMatrixReportDto,
  VerifyToolGovernanceResponse, SimulateWorkflowResponse.

[POS]
- Server security service. Wraps harness RuntimeZeroBypassWatchdog,
  GovernanceAssemblyProbe, and RecordingChatModel.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from myrm_agent_harness.core.security.governance_assembly import (
    DEFAULT_MANDATORY_MIDDLEWARES,
    GovernanceAssemblyProbe,
    GovernanceMatrixReport,
    IngressSource,
    RecordingChatModel,
    RecordingTurn,
    RuntimeZeroBypassWatchdog,
    SyntheticToolCall,
    ToolCallAssemblyTrace,
    UngovernedToolExecutionError,
    wrap_with_governance,
)

from app.schemas.governance_assembly import (
    GovernanceMatrixReportDto,
    RecordInvocationRequest,
    SimulateWorkflowRequest,
    SimulateWorkflowResponse,
    ToolCallAssemblyTraceDto,
    VerifyToolGovernanceRequest,
    VerifyToolGovernanceResponse,
)

logger = logging.getLogger(__name__)


def _trace_to_dto(trace: ToolCallAssemblyTrace) -> ToolCallAssemblyTraceDto:
    """Convert harness trace to DTO."""
    return ToolCallAssemblyTraceDto(
        trace_id=trace.trace_id,
        tool_name=trace.tool_name,
        ingress_source=trace.ingress_source.value,
        call_stack_summary=trace.call_stack_summary,
        applied_middlewares=list(trace.applied_middlewares),
        is_governed=trace.is_governed,
        bypassed_guards=list(trace.bypassed_guards),
    )


def _report_to_dto(report: GovernanceMatrixReport) -> GovernanceMatrixReportDto:
    """Convert harness matrix report to DTO."""
    return GovernanceMatrixReportDto(
        total_invocations=report.total_invocations,
        governed_invocations=report.governed_invocations,
        bypassed_invocations=report.bypassed_invocations,
        coverage_ratio=report.coverage_ratio,
        is_fully_compliant=report.is_fully_compliant,
        traces_by_ingress=dict(report.traces_by_ingress),
        violations=list(report.violations),
    )


class GovernanceAssemblyService:
    """Service auditing multi-ingress governance assembly and asserting zero-bypass."""

    def __init__(self) -> None:
        self._watchdog = RuntimeZeroBypassWatchdog()
        self._probe = GovernanceAssemblyProbe()

    @property
    def probe(self) -> GovernanceAssemblyProbe:
        """Underlying assembly probe instance."""
        return self._probe

    def record_invocation(self, req: RecordInvocationRequest) -> ToolCallAssemblyTraceDto:
        """Record an observed tool call on the execution path."""
        source = IngressSource(req.ingress_source)
        trace = self._probe.record_invocation(
            tool_name=req.tool_name,
            ingress_source=source,
            applied_middlewares=req.applied_middlewares,
            is_governed=req.is_governed,
            bypassed_guards=req.bypassed_guards,
            call_stack_summary=req.call_stack_summary,
        )
        return _trace_to_dto(trace)

    def get_matrix_report(self) -> GovernanceMatrixReportDto:
        """Generate current multi-ingress governance coverage matrix report."""
        report = self._probe.generate_matrix_report()
        return _report_to_dto(report)

    def verify_tool_governance(
        self, req: VerifyToolGovernanceRequest
    ) -> VerifyToolGovernanceResponse:
        """Verify whether a configured tool satisfies mandatory governance middlewares."""
        missing = [m for m in DEFAULT_MANDATORY_MIDDLEWARES if m not in req.applied_middlewares]
        is_valid = len(missing) == 0
        msg = (
            f"Tool '{req.tool_name}' is fully governed"
            if is_valid
            else f"Tool '{req.tool_name}' missing required guards: {missing}"
        )
        return VerifyToolGovernanceResponse(
            is_valid=is_valid,
            tool_name=req.tool_name,
            missing_middlewares=missing,
            message=msg,
        )

    def simulate_workflow(self, req: SimulateWorkflowRequest) -> SimulateWorkflowResponse:
        """Run an offline recording-model workflow to assert assembly without LLM cost."""
        ingress_source = IngressSource(req.ingress_source)
        target_tools = req.tools or ["read_data", "save_output"]

        # Build tools mapping
        tools: dict[str, Callable[..., str]] = {}
        for name in target_tools:
            def dummy_tool(tool_name: str = name, **kwargs: object) -> str:
                return f"executed::{tool_name}"

            if req.simulate_naked_tool and name == target_tools[-1]:
                # Deliberately register raw callable without governance wrapper
                tools[name] = dummy_tool
            else:
                tools[name] = wrap_with_governance(
                    dummy_tool,
                    tool_name=name,
                    ingress_source=ingress_source,
                )

        # Build scripted turns
        script_turns = [
            RecordingTurn(
                role="assistant",
                content=f"Workflow step for {req.scenario_name}",
                tool_calls=tuple(SyntheticToolCall(tool_name=name) for name in target_tools),
            )
        ]
        model = RecordingChatModel(script_turns)

        executed_tools: list[str] = []
        results: list[str] = []
        is_governed = True

        try:
            results = model.execute_scripted_workflow(
                ingress_source=ingress_source,
                watchdog=self._watchdog,
                probe=self._probe,
                tools=tools,
                prompts=[f"Trigger {req.scenario_name}"],
            )
            executed_tools = list(target_tools)
        except UngovernedToolExecutionError:
            is_governed = False
            results.append("[BLOCKED_BY_WATCHDOG]")

        report = self.get_matrix_report()
        return SimulateWorkflowResponse(
            scenario_name=req.scenario_name,
            ingress_source=ingress_source.value,
            executed_tools=executed_tools,
            is_governed=is_governed,
            results=results,
            matrix_report=report,
        )

    def reset(self) -> None:
        """Reset probe traces."""
        self._probe.clear()


_service_instance: GovernanceAssemblyService | None = None


def get_governance_assembly_service() -> GovernanceAssemblyService:
    """Obtain or initialize the singleton GovernanceAssemblyService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GovernanceAssemblyService()
    return _service_instance
