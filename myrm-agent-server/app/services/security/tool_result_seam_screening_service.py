"""
[POS] app/services/security/tool_result_seam_screening_service.py
[INPUT] app/schemas/tool_result_seam_screening.py, myrm_agent_harness.core.security.tool_result_seam_screening
[OUTPUT] ToolResultSeamScreeningService, get_tool_result_seam_screening_service

Service layer for tool result seam screening and in-place redactor suite.

Connects the physical execution seam to the harness-level screening engine,
maintains security telemetry metrics, and supports dynamic policy updates.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.tool_result_seam_screening import (
    ScreeningPolicy,
    ScreeningVerdictStatus,
    ToolResultSeamScreeningSuite,
)

from app.schemas.tool_result_seam_screening import (
    BatchToolResultScreenRequest,
    BatchToolResultScreenResponse,
    ScreeningEngineModeEnum,
    ScreeningPolicyUpdateRequest,
    ScreeningVerdictStatusEnum,
    SeamScreeningMetricsResponse,
    ToolResultScreenRequest,
    ToolResultScreenResponse,
)


class ToolResultSeamScreeningService:
    """Manages seam screening lifecycle, policy configuration, and metrics collection."""

    def __init__(self, policy: Optional[ScreeningPolicy] = None) -> None:
        self._policy = policy or ScreeningPolicy()
        self._suite = ToolResultSeamScreeningSuite(policy=self._policy)
        self._lock = threading.Lock()

        # Telemetry metrics
        self._total_requests: int = 0
        self._clean_verdicts: int = 0
        self._redacted_verdicts: int = 0
        self._fail_open_verdicts: int = 0
        self._total_latency_ms: float = 0.0
        self._total_flagged_units: int = 0

    def screen_tool_result(self, request: ToolResultScreenRequest) -> ToolResultScreenResponse:
        """Screen and in-place sanitize a single tool execution result."""
        result = self._suite.screen(tool_name=request.tool_name, tool_result=request.tool_result)

        # Map harness enum to schema enum
        status_enum_map: dict[str, ScreeningVerdictStatusEnum] = {
            ScreeningVerdictStatus.CLEAN.value: ScreeningVerdictStatusEnum.CLEAN,
            ScreeningVerdictStatus.REDACTED.value: ScreeningVerdictStatusEnum.REDACTED,
            ScreeningVerdictStatus.FAIL_OPEN.value: ScreeningVerdictStatusEnum.FAIL_OPEN,
            ScreeningVerdictStatus.BYPASS.value: ScreeningVerdictStatusEnum.BYPASS,
        }
        verdict_status = status_enum_map.get(result.verdict_status.value, ScreeningVerdictStatusEnum.CLEAN)

        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += result.latency_ms
            self._total_flagged_units += result.flagged_units
            if verdict_status == ScreeningVerdictStatusEnum.CLEAN:
                self._clean_verdicts += 1
            elif verdict_status == ScreeningVerdictStatusEnum.REDACTED:
                self._redacted_verdicts += 1
            elif verdict_status == ScreeningVerdictStatusEnum.FAIL_OPEN:
                self._fail_open_verdicts += 1

        engine_mode = (
            ScreeningEngineModeEnum.DUAL_MODE
            if result.screening_mode.value == "dual_mode"
            else ScreeningEngineModeEnum.LOCAL_ONLY
        )

        return ToolResultScreenResponse(
            tool_name=request.tool_name,
            verdict_status=verdict_status,
            screening_mode=engine_mode,
            total_units=result.total_units,
            flagged_units=result.flagged_units,
            flagged_chunk_ids=result.flagged_chunk_ids,
            redacted_content=result.redacted_content,
            latency_ms=result.latency_ms,
            reason=result.reason,
            scores=result.scores,
        )

    def batch_screen(self, request: BatchToolResultScreenRequest) -> BatchToolResultScreenResponse:
        """Process a batch of tool results concurrently or sequentially."""
        responses: list[ToolResultScreenResponse] = []
        total_redacted = 0
        aggregate_latency = 0.0

        for item in request.items:
            res = self.screen_tool_result(item)
            responses.append(res)
            if res.verdict_status == ScreeningVerdictStatusEnum.REDACTED:
                total_redacted += 1
            aggregate_latency += res.latency_ms

        return BatchToolResultScreenResponse(
            results=responses,
            total_screened=len(responses),
            total_redacted=total_redacted,
            aggregate_latency_ms=aggregate_latency,
        )

    def update_policy(self, req: ScreeningPolicyUpdateRequest) -> None:
        """Dynamically update screening policy parameters."""
        with self._lock:
            self._policy = ScreeningPolicy(
                threshold=req.threshold,
                timeout_seconds=req.timeout_seconds,
                max_chunk_chars=req.max_chunk_chars,
                fast_model_enabled=req.fast_model_enabled,
                fail_open_on_error=req.fail_open_on_error,
            )
            self._suite = ToolResultSeamScreeningSuite(policy=self._policy)

    def get_metrics(self) -> SeamScreeningMetricsResponse:
        """Retrieve aggregated security telemetry and operational screening metrics."""
        with self._lock:
            avg_lat = (self._total_latency_ms / self._total_requests) if self._total_requests > 0 else 0.0
            return SeamScreeningMetricsResponse(
                total_requests=self._total_requests,
                clean_verdicts=self._clean_verdicts,
                redacted_verdicts=self._redacted_verdicts,
                fail_open_verdicts=self._fail_open_verdicts,
                avg_latency_ms=round(avg_lat, 3),
                total_flagged_units=self._total_flagged_units,
            )


_global_service: Optional[ToolResultSeamScreeningService] = None
_global_lock = threading.Lock()


def get_tool_result_seam_screening_service() -> ToolResultSeamScreeningService:
    """Get the singleton instance of ToolResultSeamScreeningService."""
    global _global_service
    if _global_service is None:
        with _global_lock:
            if _global_service is None:
                _global_service = ToolResultSeamScreeningService()
    return _global_service
