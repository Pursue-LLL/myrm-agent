"""
[POS] app/services/security/memory_post_fetch_screening_service.py
[INPUT] app/schemas/memory_post_fetch_screening.py, myrm_agent_harness.core.security.memory_post_fetch_screening
[OUTPUT] MemoryPostFetchScreeningService, get_memory_post_fetch_screening_service

Service layer for memory retrieval post-fetch injection screening suite.

Bridges memory search/retrieval operations to the harness-level screening gate,
tracks telemetry statistics, and maintains quarantine records.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.memory_post_fetch_screening import (
    MemoryPassageUnit,
    MemoryRetrievalPostFetchScreeningSuite,
    MemoryScreeningPolicy,
    ScreeningPathMode,
)

from app.schemas.memory_post_fetch_screening import (
    MemoryPassageItem,
    MemoryScreeningMetricsResponse,
    MemoryScreeningPolicyUpdateRequest,
    QuarantinedPassageReportSchema,
    ScreeningPathModeEnum,
    ScreenMemoryPassagesRequest,
    ScreenMemoryPassagesResponse,
)


class MemoryPostFetchScreeningService:
    """Singleton service for memory passage injection screening and quarantine auditing."""

    def __init__(self, policy: Optional[MemoryScreeningPolicy] = None) -> None:
        self._policy = policy or MemoryScreeningPolicy()
        self._suite = MemoryRetrievalPostFetchScreeningSuite(policy=self._policy)
        self._lock = threading.Lock()

        # Telemetry metrics
        self._total_passages_evaluated: int = 0
        self._clean_passages_count: int = 0
        self._quarantined_passages_count: int = 0
        self._total_requests: int = 0
        self._total_latency_ms: float = 0.0
        self._jev_path_count: int = 0
        self._local_path_count: int = 0

    def screen_passages(self, request: ScreenMemoryPassagesRequest) -> ScreenMemoryPassagesResponse:
        """Screen candidate retrieved memory passages and isolate toxic injection attempts."""
        # Convert schema items to harness units
        harness_units = [
            MemoryPassageUnit(
                passage_id=p.passage_id,
                content=p.content,
                source_uri=p.source_uri,
                relevance_score=p.relevance_score,
                created_at=p.created_at,
            )
            for p in request.passages
        ]

        result = self._suite.screen_retrieved_passages(harness_units)

        # Convert clean units back to schema items
        clean_items = [
            MemoryPassageItem(
                passage_id=u.passage_id,
                content=u.content,
                source_uri=u.source_uri,
                relevance_score=u.relevance_score,
                created_at=u.created_at,
            )
            for u in result.clean_passages
        ]

        # Convert quarantine reports
        pathway_enum_map: dict[str, ScreeningPathModeEnum] = {
            ScreeningPathMode.JEV_AND_LOCAL.value: ScreeningPathModeEnum.JEV_AND_LOCAL,
            ScreeningPathMode.LOCAL_ONLY.value: ScreeningPathModeEnum.LOCAL_ONLY,
            ScreeningPathMode.NONE.value: ScreeningPathModeEnum.NONE,
        }
        pathway_enum = pathway_enum_map.get(result.pathway_taken.value, ScreeningPathModeEnum.LOCAL_ONLY)

        quarantine_reports = [
            QuarantinedPassageReportSchema(
                passage_id=r.passage_id,
                source_uri=r.source_uri,
                snippet=r.snippet,
                rejection_reason=r.rejection_reason,
                pathway_used=pathway_enum_map.get(r.pathway_used.value, ScreeningPathModeEnum.LOCAL_ONLY),
                threat_category=r.threat_category,
                detected_at=r.detected_at,
            )
            for r in result.quarantined_reports
        ]

        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += result.latency_ms
            self._total_passages_evaluated += result.total_evaluated
            self._clean_passages_count += len(clean_items)
            self._quarantined_passages_count += len(quarantine_reports)
            if pathway_enum == ScreeningPathModeEnum.JEV_AND_LOCAL:
                self._jev_path_count += 1
            else:
                self._local_path_count += 1

        return ScreenMemoryPassagesResponse(
            total_evaluated=result.total_evaluated,
            clean_passages=clean_items,
            quarantined_reports=quarantine_reports,
            pathway_taken=pathway_enum,
            latency_ms=result.latency_ms,
            degradation_reason=result.degradation_reason,
        )

    def get_quarantine_records(self, limit: int = 50) -> list[QuarantinedPassageReportSchema]:
        """Fetch historical quarantined passage reports."""
        records = self._suite.get_quarantine_records(limit=limit)
        pathway_enum_map: dict[str, ScreeningPathModeEnum] = {
            ScreeningPathMode.JEV_AND_LOCAL.value: ScreeningPathModeEnum.JEV_AND_LOCAL,
            ScreeningPathMode.LOCAL_ONLY.value: ScreeningPathModeEnum.LOCAL_ONLY,
            ScreeningPathMode.NONE.value: ScreeningPathModeEnum.NONE,
        }
        return [
            QuarantinedPassageReportSchema(
                passage_id=r.passage_id,
                source_uri=r.source_uri,
                snippet=r.snippet,
                rejection_reason=r.rejection_reason,
                pathway_used=pathway_enum_map.get(r.pathway_used.value, ScreeningPathModeEnum.LOCAL_ONLY),
                threat_category=r.threat_category,
                detected_at=r.detected_at,
            )
            for r in records
        ]

    def update_policy(self, req: MemoryScreeningPolicyUpdateRequest) -> None:
        """Dynamically update memory screening policy parameters."""
        with self._lock:
            self._policy = MemoryScreeningPolicy(
                threshold=req.threshold,
                remote_timeout_seconds=req.remote_timeout_seconds,
                remote_scorer_enabled=req.remote_scorer_enabled,
                quarantine_toxic_passages=req.quarantine_toxic_passages,
                enable_url_exfiltration_scan=req.enable_url_exfiltration_scan,
                enable_command_risk_scan=req.enable_command_risk_scan,
            )
            self._suite = MemoryRetrievalPostFetchScreeningSuite(policy=self._policy)

    def get_metrics(self) -> MemoryScreeningMetricsResponse:
        """Retrieve aggregated operational telemetry and threat mitigation metrics."""
        with self._lock:
            avg_lat = (self._total_latency_ms / self._total_requests) if self._total_requests > 0 else 0.0
            return MemoryScreeningMetricsResponse(
                total_passages_evaluated=self._total_passages_evaluated,
                clean_passages_count=self._clean_passages_count,
                quarantined_passages_count=self._quarantined_passages_count,
                avg_latency_ms=round(avg_lat, 3),
                jev_path_count=self._jev_path_count,
                local_path_count=self._local_path_count,
            )


_global_service: Optional[MemoryPostFetchScreeningService] = None
_global_lock = threading.Lock()


def get_memory_post_fetch_screening_service() -> MemoryPostFetchScreeningService:
    """Get the singleton instance of MemoryPostFetchScreeningService."""
    global _global_service
    if _global_service is None:
        with _global_lock:
            if _global_service is None:
                _global_service = MemoryPostFetchScreeningService()
    return _global_service
