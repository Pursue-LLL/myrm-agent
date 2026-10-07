# [POS]: app/services/memory/experience_observability_service.py
# [INPUT]: app.schemas.experience_observability, myrm_agent_harness.toolkits.memory.experience_observability
# [OUTPUT]: ExperienceObservabilityService, get_experience_observability_service

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    ExperienceObservabilityMetric,
    ExperienceObservabilityTracker,
    HostAccessChannel,
    SessionTraceEvidence,
    ZeroRefactorHostPlugin,
)

from app.schemas.experience_observability import (
    ExperienceObservabilityMetricDTO,
    HostPluginConfigDTO,
    ObservabilityDashboardResponseDTO,
    RecordEffectEventRequest,
    RecordRecallEventRequest,
    SessionTraceEvidenceDTO,
    UpdatePluginConfigRequest,
)

logger = logging.getLogger(__name__)


def _metric_to_dto(m: ExperienceObservabilityMetric) -> ExperienceObservabilityMetricDTO:
    """Map internal domain metric to API DTO."""
    return ExperienceObservabilityMetricDTO(
        entry_id=m.entry_id,
        name=m.name,
        source_session_id=m.source_session_id,
        access_channel=m.access_channel.value,
        recall_count=m.recall_count,
        injection_count=m.injection_count,
        success_count=m.success_count,
        dispute_count=m.dispute_count,
        success_rate=m.success_rate,
        effect_status=m.effect_status.value,
        last_observed_at=m.last_observed_at,
    )


def _trace_to_dto(t: SessionTraceEvidence) -> SessionTraceEvidenceDTO:
    """Map internal session evidence trace to API DTO."""
    return SessionTraceEvidenceDTO(
        session_id=t.session_id,
        title=t.title,
        trajectory_summary=t.trajectory_summary,
        key_evidence_snippets=list(t.key_evidence_snippets),
        agent_role=t.agent_role,
        timestamp=t.timestamp,
    )


class ExperienceObservabilityService:
    """Application service coordinating experience observability metrics and zero-refactor plugin."""

    def __init__(
        self,
        tracker: ExperienceObservabilityTracker | None = None,
        plugin: ZeroRefactorHostPlugin | None = None,
    ) -> None:
        self._tracker = tracker if tracker is not None else ExperienceObservabilityTracker()
        self._plugin = plugin if plugin is not None else ZeroRefactorHostPlugin(tracker=self._tracker)

    def get_dashboard(self) -> ObservabilityDashboardResponseDTO:
        """Retrieve full dashboard aggregating experience items, effect distribution, and plugin state."""
        raw_metrics = self._tracker.list_metrics()
        dtos = [_metric_to_dto(m) for m in raw_metrics]

        total_recalls = sum(m.recall_count for m in dtos)
        total_injections = sum(m.injection_count for m in dtos)
        avg_success_rate = (
            round(sum(m.success_rate for m in dtos) / len(dtos), 3) if dtos else 1.0
        )

        cfg = self.get_plugin_config()

        return ObservabilityDashboardResponseDTO(
            status="ok",
            total_experiences_tracked=len(dtos),
            overall_success_rate=avg_success_rate,
            total_recalls=total_recalls,
            total_injections=total_injections,
            plugin_config=cfg,
            metrics=dtos,
        )

    def list_metrics(
        self,
        channel_str: str | None = None,
        status_str: str | None = None,
    ) -> list[ExperienceObservabilityMetricDTO]:
        """List tracked experience metrics with optional channel and status filtering."""
        raw_metrics = self._tracker.list_metrics()
        dtos = [_metric_to_dto(m) for m in raw_metrics]

        if channel_str:
            dtos = [m for m in dtos if m.access_channel == channel_str]
        if status_str:
            dtos = [m for m in dtos if m.effect_status == status_str]

        return dtos

    def get_metric(self, entry_id: str) -> ExperienceObservabilityMetricDTO | None:
        """Get metric details for an individual experience item."""
        metric = self._tracker.get_metric(entry_id)
        if metric is None:
            return None
        return _metric_to_dto(metric)

    def get_trace_evidence(self, session_id: str) -> SessionTraceEvidenceDTO | None:
        """Retrieve originating session evidence trace."""
        trace = self._tracker.get_trace_evidence(session_id)
        if trace is None:
            return None
        return _trace_to_dto(trace)

    def get_plugin_config(self) -> HostPluginConfigDTO:
        """Get current host plugin configuration."""
        cfg = self._plugin.config
        return HostPluginConfigDTO(
            enabled=cfg.enabled,
            active_channel=cfg.active_channel.value,
            auto_warmup=cfg.auto_warmup,
            auto_capture=cfg.auto_capture,
            auto_commit=cfg.auto_commit,
            monitored_host=cfg.monitored_host,
        )

    def update_plugin_config(self, req: UpdatePluginConfigRequest) -> HostPluginConfigDTO:
        """Update host plugin configuration."""
        ch: HostAccessChannel | None = None
        if req.active_channel is not None:
            try:
                ch = HostAccessChannel(req.active_channel)
            except ValueError:
                ch = None

        cfg = self._plugin.update_config(
            enabled=req.enabled,
            active_channel=ch,
            auto_warmup=req.auto_warmup,
            auto_capture=req.auto_capture,
            auto_commit=req.auto_commit,
            monitored_host=req.monitored_host,
        )
        return HostPluginConfigDTO(
            enabled=cfg.enabled,
            active_channel=cfg.active_channel.value,
            auto_warmup=cfg.auto_warmup,
            auto_capture=cfg.auto_capture,
            auto_commit=cfg.auto_commit,
            monitored_host=cfg.monitored_host,
        )

    def record_recall_event(self, req: RecordRecallEventRequest) -> ExperienceObservabilityMetricDTO:
        """Record an experience recall event hit."""
        try:
            channel = HostAccessChannel(req.channel)
        except ValueError:
            channel = HostAccessChannel.PLUGIN

        metric = self._tracker.record_recall(entry_id=req.entry_id, channel=channel)
        return _metric_to_dto(metric)

    def record_effect_event(self, req: RecordEffectEventRequest) -> ExperienceObservabilityMetricDTO:
        """Record task outcome or user dispute following experience injection."""
        metric = self._tracker.record_effect(
            entry_id=req.entry_id,
            is_success=req.is_success,
            is_dispute=req.is_dispute,
        )
        return _metric_to_dto(metric)


@lru_cache(maxsize=1)
def get_experience_observability_service() -> ExperienceObservabilityService:
    """Obtain singleton instance of ExperienceObservabilityService."""
    return ExperienceObservabilityService()
