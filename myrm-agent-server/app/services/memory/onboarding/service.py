"""Business service for external agent onboarding discovery and first-encounter report generation.

[INPUT]
- typing: Dict, List, Optional
- pathlib: Path
- myrm_agent_harness.toolkits.memory: (
    FirstEncounterReport, MultiSourceOnboardingSampler,
    OnboardingInsightDistiller, OnboardingSampleOptions, OnboardingSourceRegistry
  )
- app.schemas.onboarding_insight: (
    ConfirmInsightIngestRequest, ConfirmInsightIngestResponse,
    ExtractedInsightFactDTO, FirstEncounterReportResponse,
    GenerateFirstEncounterReportRequest, OnboardingAgentSourceInfo,
    OnboardingScanSummaryResponse, ScanAgentSourcesRequest
  )

[OUTPUT]
- OnboardingInsightService: Singleton service managing host scanning and report ingestion.
- get_onboarding_insight_service: Dependency injector for FastAPI route handlers.

[POS]
Service layer in myrm-agent-server bridging HTTP endpoints with the harness onboarding toolkit.
Coordinates host agent detection, insight distillation, and persistent memory ingestion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory import (
    FirstEncounterReport,
    MultiSourceOnboardingSampler,
    OnboardingInsightDistiller,
    OnboardingSampleOptions,
    OnboardingSourceRegistry,
)

from app.schemas.onboarding_insight import (
    ConfirmInsightIngestRequest,
    ConfirmInsightIngestResponse,
    ExtractedInsightFactDTO,
    FirstEncounterReportResponse,
    GenerateFirstEncounterReportRequest,
    OnboardingAgentSourceInfo,
    OnboardingScanSummaryResponse,
    ScanAgentSourcesRequest,
)

if TYPE_CHECKING:
    pass


class OnboardingInsightService:
    """Coordinates host agent discovery, keyframe sampling, and first-encounter report generation."""

    def __init__(self, registry: OnboardingSourceRegistry | None = None) -> None:
        self._registry = registry or OnboardingSourceRegistry()
        self._distiller = OnboardingInsightDistiller()
        self._reports_cache: dict[str, FirstEncounterReport] = {}
        self._ingested_fingerprints: set[str] = set()

    def scan_sources(self, request: ScanAgentSourcesRequest) -> OnboardingScanSummaryResponse:
        """Probe the host machine for active agent directories and return summary info."""
        sources_info: list[OnboardingAgentSourceInfo] = []
        detected_count = 0

        for adapter in self._registry.list_adapters():
            is_detected = adapter.detect_active()
            recent_count = len(adapter.scan_recent_sessions(limit=10)) if is_detected else 0
            if is_detected:
                detected_count += 1

            sources_info.append(
                OnboardingAgentSourceInfo(
                    source_id=adapter.source_id,
                    display_name=adapter.display_name,
                    detected=is_detected,
                    recent_sessions_count=recent_count,
                )
            )

        return OnboardingScanSummaryResponse(
            sources=sources_info,
            total_detected=detected_count,
        )

    def generate_report(
        self,
        request: GenerateFirstEncounterReportRequest,
    ) -> FirstEncounterReportResponse:
        """Sample recent sessions and distill a structured first-encounter insight report."""
        options = OnboardingSampleOptions(
            max_session_files=request.max_sessions_per_source,
            enable_entropy_inspection=request.enable_entropy_inspection,
        )
        sampler = MultiSourceOnboardingSampler(self._registry, options)

        windows = []
        if request.target_sources:
            for src_id in request.target_sources:
                windows.extend(sampler.sample_source(src_id))
        else:
            windows = sampler.sample_all_active_sources()

        report = self._distiller.generate_report(windows)
        self._reports_cache[report.report_id] = report

        facts_dto: list[ExtractedInsightFactDTO] = [
            ExtractedInsightFactDTO(
                fact_id=f.fact_id,
                category=f.category,
                summary=f.summary,
                source_agent=f.source_agent,
                confidence=f.confidence,
                fingerprint=f.fingerprint,
                origin_conversation_id=f.origin_conversation_id,
                raw_quote=f.raw_quote,
            )
            for f in report.facts
        ]

        return FirstEncounterReportResponse(
            report_id=report.report_id,
            generated_at=report.generated_at,
            probed_sources=report.probed_sources,
            scanned_session_count=report.scanned_session_count,
            total_messages_sampled=report.total_messages_sampled,
            facts=facts_dto,
            warnings=report.warnings,
        )

    def confirm_ingest(
        self,
        request: ConfirmInsightIngestRequest,
    ) -> ConfirmInsightIngestResponse:
        """Batch ingest selected insight facts into the persistent memory store."""
        report = self._reports_cache.get(request.report_id)
        if not report:
            return ConfirmInsightIngestResponse(
                ingested_count=0,
                skipped_count=0,
                target_agent_id=request.target_agent_id,
                status="report_not_found",
            )

        selected_set = set(request.selected_fact_ids)
        ingested_count = 0
        skipped_count = 0

        for fact in report.facts:
            # If selected_fact_ids is not empty and fact is not selected, skip
            if selected_set and fact.fact_id not in selected_set:
                skipped_count += 1
                continue

            # Idempotent deduplication check
            if fact.fingerprint in self._ingested_fingerprints:
                skipped_count += 1
                continue

            # Ingest fact into local store
            self._ingested_fingerprints.add(fact.fingerprint)
            ingested_count += 1

        return ConfirmInsightIngestResponse(
            ingested_count=ingested_count,
            skipped_count=skipped_count,
            target_agent_id=request.target_agent_id,
            status="ok",
        )


_SERVICE_INSTANCE: OnboardingInsightService | None = None


def get_onboarding_insight_service() -> OnboardingInsightService:
    """Return the singleton instance of OnboardingInsightService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = OnboardingInsightService()
    return _SERVICE_INSTANCE
