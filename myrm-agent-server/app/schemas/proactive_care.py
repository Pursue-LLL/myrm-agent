"""[POS]: app/schemas/proactive_care.py
[INPUT]: HTTP requests for health telemetry sync, vitality evaluation, and proactive schedule rebalancing.
[OUTPUT]: Pydantic schemas for health records, vitality reports, schedule rebalance plans, and care alerts.
"""

from pydantic import BaseModel, Field


class SyncHealthMetricsRequest(BaseModel):
    """Payload to ingest objective physiological metrics from mobile health systems."""

    metric_id: str | None = Field(default=None, description="Optional unique identifier.")
    user_id: str = Field(default="default_user", description="Identifier of the user.")
    sleep_duration_hours: float = Field(..., ge=0.0, le=24.0, description="Total sleep hours.")
    deep_sleep_ratio: float = Field(
        default=0.20, ge=0.0, le=1.0, description="Deep sleep ratio (0.0 - 1.0)."
    )
    daily_steps: int = Field(default=6000, ge=0, description="Recorded daily step count.")
    resting_heart_rate: int = Field(
        default=70, ge=30, le=220, description="Resting heart rate in bpm."
    )
    recorded_at_iso: str = Field(default="", description="ISO timestamp of measurement.")


class RecordConversationalCueRequest(BaseModel):
    """Payload to log subtle conversational fatigue cues."""

    user_id: str = Field(default="default_user", description="Identifier of the user.")
    cue_text: str = Field(..., min_length=1, description="Casual fatigue/sleep statement.")


class HealthMetricsRecordDTO(BaseModel):
    """DTO representing a stored physiological metric record."""

    metric_id: str
    user_id: str
    timestamp: float
    sleep_duration_hours: float
    deep_sleep_ratio: float
    daily_steps: int
    resting_heart_rate: int
    recorded_at_iso: str


class VitalityReportResponse(BaseModel):
    """Response containing vitality assessment report and causal analysis."""

    assessment_id: str
    user_id: str
    timestamp: float
    vitality_score: float
    fatigue_level: str
    causal_factors: list[str]
    conversational_cues: list[str]
    recommendations: list[str]


class ScheduleTaskDTO(BaseModel):
    """DTO for an individual scheduled task or training session."""

    task_id: str
    title: str
    scheduled_date: str
    intensity_level: int = Field(default=3, ge=1, le=5)
    category: str = Field(default="general")
    is_flexible: bool = True
    original_duration_minutes: int = 60
    adjusted_duration_minutes: int = 60
    status: str = "active"


class RebalanceScheduleRequest(BaseModel):
    """Request to initiate dynamic schedule rebalancing and proactive care."""

    user_id: str = Field(default="default_user", description="Target user identifier.")
    tasks: list[ScheduleTaskDTO] = Field(
        default_factory=list, description="Candidate schedule tasks to rebalance."
    )
    force_notify: bool = Field(
        default=False, description="Whether to bypass cooldown gate and force notification."
    )


class CareNotificationDTO(BaseModel):
    """DTO for an empathetic proactive care alert."""

    notification_id: str
    user_id: str
    timestamp: float
    fatigue_level: str
    title: str
    content_message: str
    suggested_actions: list[str]
    is_read: bool


class RebalanceScheduleResponse(BaseModel):
    """Response encapsulating the rebalance plan and optional delivered care notification."""

    plan_id: str
    user_id: str
    created_at: float
    fatigue_level: str
    load_reduction_ratio: float
    tasks_modified: list[ScheduleTaskDTO]
    summary: str
    care_notification: CareNotificationDTO | None = None


class CareNotificationListResponse(BaseModel):
    """List of stored proactive care notifications."""

    total_count: int
    notifications: list[CareNotificationDTO]
