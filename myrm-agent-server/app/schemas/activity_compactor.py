"""Schemas and DTOs for Hierarchical Time-Window Activity Compactor pipeline.

[INPUT]
- External: pydantic, datetime

[OUTPUT]
- IngestActivityEventRequestDTO: Payload to ingest a raw desktop activity event.
- MicroActivitySliceDTO: 10-minute algorithmic folded slice DTO (0 LLM Token).
- MacroMilestoneFoldDTO: 6-hour consolidated macro milestone fold DTO.
- DailyPreferenceArchiveDTO: 24-hour synthesized long-term facts & preferences DTO.
- CompactorPipelineTelemetryDTO: Real-time telemetry tracking compression ratio & token savings.

[POS]
Server data transfer objects for Topic 01 Item 87 (ChatGPT Desktop Skysight-style 10min/6h/24h compaction).
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class IngestActivityEventRequestDTO(BaseModel):
    """Payload to ingest a raw activity observation event."""

    app_name: str = Field(description="Active application name (e.g., VSCode, Chrome, Terminal)")
    window_title: str = Field(description="Active window title or tab header")
    action_type: str = Field(default="keystroke_burst", description="Action classification")
    event_payload: str = Field(default="", description="Command, typed content, or URL")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Dwell duration in seconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Occurrence timestamp")


class MicroActivitySliceDTO(BaseModel):
    """10-minute algorithmic deduplicated and folded activity slice (0 Token cost)."""

    slice_id: str
    start_time: datetime
    end_time: datetime
    primary_app: str
    raw_event_count: int
    folded_summary: str
    unique_windows: list[str] = Field(default_factory=list)
    is_idle: bool = False
    active_minutes: float = 0.0


class MacroMilestoneFoldDTO(BaseModel):
    """6-hour consolidated macro milestone distilled from ~36 micro slices."""

    fold_id: str
    start_time: datetime
    end_time: datetime
    milestone_summary: str
    key_activities: list[str] = Field(default_factory=list)
    micro_slices_count: int
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.95


class DailyPreferenceArchiveDTO(BaseModel):
    """24-hour long-term synthesized facts and preference updates for persistent memory."""

    archive_id: str
    date_str: str
    consolidated_facts: list[str] = Field(default_factory=list)
    preference_updates: list[str] = Field(default_factory=list)
    total_raw_events_processed: int
    macro_folds_count: int


class CompactorPipelineTelemetryDTO(BaseModel):
    """Telemetry tracking compaction ratio and token cost savings."""

    total_raw_events: int = 0
    total_micro_slices: int = 0
    total_macro_folds: int = 0
    idle_events_dropped: int = 0
    estimated_tokens_saved: int = 0
    compression_ratio: float = 0.0


class TriggerMicroFoldRequestDTO(BaseModel):
    """Request payload to trigger a 10-minute micro fold."""

    force: bool = Field(default=True, description="Whether to flush current buffer into a slice")


class TriggerMacroDistillRequestDTO(BaseModel):
    """Request payload to trigger a 6-hour macro distillation."""

    hours_back: int = Field(default=6, ge=1, le=24, description="Lookback window in hours")


class SynthesizeDailyArchiveRequestDTO(BaseModel):
    """Request payload to synthesize a 24-hour daily archive."""

    date_str: str | None = Field(default=None, description="Target date string YYYY-MM-DD")
