"""Service managing Hierarchical Activity Compactor pipeline and sliding windows.

[INPUT]
- Internal: app.schemas.activity_compactor
- External: myrm_agent_harness.toolkits.memory.activity_compactor, uuid, datetime

[OUTPUT]
- ActivityCompactorService: Singleton managing raw ingestion, 10m micro folding, 6h distillation, and 24h archiving.
- get_activity_compactor_service(): Singleton provider.

[POS]
Server service layer for Topic 01 Item 87 (ChatGPT Desktop Skysight-style 10min/6h/24h compaction).
"""

import uuid
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.memory import (
    ActivityActionType,
    CompactorPipelineConfig,
    HierarchicalActivityCompactorPipeline,
    RawActivityEvent,
)

from app.schemas.activity_compactor import (
    CompactorPipelineTelemetryDTO,
    DailyPreferenceArchiveDTO,
    IngestActivityEventRequestDTO,
    MacroMilestoneFoldDTO,
    MicroActivitySliceDTO,
)


class ActivityCompactorService:
    """Service orchestrating event streams into 10min micro slices and 6h macro milestone folds."""

    def __init__(self, config: CompactorPipelineConfig | None = None) -> None:
        self.pipeline = HierarchicalActivityCompactorPipeline(config=config)

    def ingest_event(self, req: IngestActivityEventRequestDTO) -> None:
        """Stream an activity event into the pipeline raw buffer."""
        action_enum = ActivityActionType.KEYSTROKE_BURST
        try:
            action_enum = ActivityActionType(req.action_type)
        except ValueError:
            pass

        raw_event = RawActivityEvent(
            event_id=f"ev_{uuid.uuid4().hex[:8]}",
            timestamp=req.timestamp,
            app_name=req.app_name,
            window_title=req.window_title,
            action_type=action_enum,
            event_payload=req.event_payload,
            duration_seconds=req.duration_seconds,
        )
        self.pipeline.ingest_event(raw_event)

    def flush_micro_fold(self) -> MicroActivitySliceDTO:
        """Trigger algorithmic 10-minute micro fold (0 Token cost)."""
        slice_obj = self.pipeline.flush_micro_window()
        return MicroActivitySliceDTO(
            slice_id=slice_obj.slice_id,
            start_time=slice_obj.start_time,
            end_time=slice_obj.end_time,
            primary_app=slice_obj.primary_app,
            raw_event_count=slice_obj.raw_event_count,
            folded_summary=slice_obj.folded_summary,
            unique_windows=slice_obj.unique_windows,
            is_idle=slice_obj.is_idle,
            active_minutes=slice_obj.active_minutes,
        )

    def distill_macro_window(self, hours_back: int = 6) -> MacroMilestoneFoldDTO:
        """Distill buffered micro slices into a 6-hour macro milestone fold."""
        now = datetime.now(UTC)
        start = now - timedelta(hours=hours_back)
        fold_obj = self.pipeline.distill_macro_window(window_start=start, window_end=now)
        return MacroMilestoneFoldDTO(
            fold_id=fold_obj.fold_id,
            start_time=fold_obj.start_time,
            end_time=fold_obj.end_time,
            milestone_summary=fold_obj.milestone_summary,
            key_activities=fold_obj.key_activities,
            micro_slices_count=fold_obj.micro_slices_count,
            tags=fold_obj.tags,
            confidence=fold_obj.confidence,
        )

    def synthesize_daily_archive(self, date_str: str | None = None) -> DailyPreferenceArchiveDTO:
        """Synthesize daily facts and long-term user preferences from all macro folds."""
        archive_obj = self.pipeline.synthesize_daily_archive(date_str=date_str)
        return DailyPreferenceArchiveDTO(
            archive_id=archive_obj.archive_id,
            date_str=archive_obj.date_str,
            consolidated_facts=archive_obj.consolidated_facts,
            preference_updates=archive_obj.preference_updates,
            total_raw_events_processed=archive_obj.total_raw_events_processed,
            macro_folds_count=archive_obj.macro_folds_count,
        )

    def get_recent_slices(self, limit: int = 50) -> list[MicroActivitySliceDTO]:
        """Return recent micro activity slices."""
        return [
            MicroActivitySliceDTO(
                slice_id=s.slice_id,
                start_time=s.start_time,
                end_time=s.end_time,
                primary_app=s.primary_app,
                raw_event_count=s.raw_event_count,
                folded_summary=s.folded_summary,
                unique_windows=s.unique_windows,
                is_idle=s.is_idle,
                active_minutes=s.active_minutes,
            )
            for s in self.pipeline.get_micro_slices(limit=limit)
        ]

    def get_recent_folds(self, limit: int = 20) -> list[MacroMilestoneFoldDTO]:
        """Return recent macro milestone folds."""
        return [
            MacroMilestoneFoldDTO(
                fold_id=f.fold_id,
                start_time=f.start_time,
                end_time=f.end_time,
                milestone_summary=f.milestone_summary,
                key_activities=f.key_activities,
                micro_slices_count=f.micro_slices_count,
                tags=f.tags,
                confidence=f.confidence,
            )
            for f in self.pipeline.get_macro_folds(limit=limit)
        ]

    def get_telemetry(self) -> CompactorPipelineTelemetryDTO:
        """Get current pipeline telemetry and token savings statistics."""
        t = self.pipeline.get_telemetry()
        return CompactorPipelineTelemetryDTO(
            total_raw_events=t.total_raw_events,
            total_micro_slices=t.total_micro_slices,
            total_macro_folds=t.total_macro_folds,
            idle_events_dropped=t.idle_events_dropped,
            estimated_tokens_saved=t.estimated_tokens_saved,
            compression_ratio=t.compression_ratio,
        )

    def reset_state(self) -> None:
        """Reset internal pipeline buffer and history."""
        self.pipeline.reset()


_activity_service_instance: ActivityCompactorService | None = None


def get_activity_compactor_service() -> ActivityCompactorService:
    """Get singleton instance of ActivityCompactorService."""
    global _activity_service_instance
    if _activity_service_instance is None:
        _activity_service_instance = ActivityCompactorService()
    return _activity_service_instance
