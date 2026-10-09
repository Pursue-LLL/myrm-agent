"""[POS]: app/api/memory/proactive_care.py
[INPUT]: FastAPI HTTP requests for health telemetry sync, vitality assessment, and proactive schedule rebalancing.
[OUTPUT]: Strongly-typed JSON responses conforming to proactive care API contracts.
"""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    CareNotification,
    HealthMetricsRecord,
    ProactiveCareRebalancingService,
    ScheduleTaskItem,
)

from app.schemas.proactive_care import (
    CareNotificationDTO,
    CareNotificationListResponse,
    HealthMetricsRecordDTO,
    RebalanceScheduleRequest,
    RebalanceScheduleResponse,
    RecordConversationalCueRequest,
    ScheduleTaskDTO,
    SyncHealthMetricsRequest,
    VitalityReportResponse,
)
from app.services.memory.proactive_care import get_proactive_care_service

router = APIRouter(prefix="/proactive-care", tags=["memory-proactive-care"])


def _to_health_dto(rec: HealthMetricsRecord) -> HealthMetricsRecordDTO:
    return HealthMetricsRecordDTO(
        metric_id=rec.metric_id,
        user_id=rec.user_id,
        timestamp=rec.timestamp,
        sleep_duration_hours=rec.sleep_duration_hours,
        deep_sleep_ratio=rec.deep_sleep_ratio,
        daily_steps=rec.daily_steps,
        resting_heart_rate=rec.resting_heart_rate,
        recorded_at_iso=rec.recorded_at_iso,
    )


def _to_care_dto(notif: CareNotification) -> CareNotificationDTO:
    return CareNotificationDTO(
        notification_id=notif.notification_id,
        user_id=notif.user_id,
        timestamp=notif.timestamp,
        fatigue_level=notif.fatigue_level.value,
        title=notif.title,
        content_message=notif.content_message,
        suggested_actions=notif.suggested_actions,
        is_read=notif.is_read,
    )


def _to_task_dto(task: ScheduleTaskItem) -> ScheduleTaskDTO:
    return ScheduleTaskDTO(
        task_id=task.task_id,
        title=task.title,
        scheduled_date=task.scheduled_date,
        intensity_level=task.intensity_level,
        category=task.category,
        is_flexible=task.is_flexible,
        original_duration_minutes=task.original_duration_minutes,
        adjusted_duration_minutes=task.adjusted_duration_minutes,
        status=task.status,
    )


@router.post("/sync-health", response_model=HealthMetricsRecordDTO)
def sync_health_telemetry(
    request: SyncHealthMetricsRequest,
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> HealthMetricsRecordDTO:
    """Ingest objective physiological health metrics from mobile systems."""
    metric_id = request.metric_id or f"metric-{uuid.uuid4().hex[:10]}"
    record = HealthMetricsRecord(
        metric_id=metric_id,
        user_id=request.user_id,
        timestamp=time.time(),
        sleep_duration_hours=request.sleep_duration_hours,
        deep_sleep_ratio=request.deep_sleep_ratio,
        daily_steps=request.daily_steps,
        resting_heart_rate=request.resting_heart_rate,
        recorded_at_iso=request.recorded_at_iso,
    )
    saved = service.sync_health_metrics(record)
    return _to_health_dto(saved)


@router.post("/record-cue")
def record_fatigue_cue(
    request: RecordConversationalCueRequest,
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> dict[str, bool | str]:
    """Record a casual conversational fatigue or sleep deprivation cue."""
    service.record_conversational_cue(
        cue_text=request.cue_text,
        user_id=request.user_id,
    )
    return {"status": True, "recorded_cue": request.cue_text}


@router.get("/vitality-report", response_model=VitalityReportResponse)
def get_vitality_report(
    user_id: str = "default_user",
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> VitalityReportResponse:
    """Evaluate current vitality score and multi-modal fatigue causality report."""
    report = service.evaluate_vitality(user_id=user_id)
    return VitalityReportResponse(
        assessment_id=report.assessment_id,
        user_id=report.user_id,
        timestamp=report.timestamp,
        vitality_score=report.vitality_score,
        fatigue_level=report.fatigue_level.value,
        causal_factors=report.causal_factors,
        conversational_cues=report.conversational_cues,
        recommendations=report.recommendations,
    )


@router.post("/rebalance-schedule", response_model=RebalanceScheduleResponse)
def rebalance_schedule(
    request: RebalanceScheduleRequest,
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> RebalanceScheduleResponse:
    """Proactively adjust flexible schedule intensity and generate empathetic care notification."""
    tasks = [
        ScheduleTaskItem(
            task_id=t.task_id,
            title=t.title,
            scheduled_date=t.scheduled_date,
            intensity_level=t.intensity_level,
            category=t.category,
            is_flexible=t.is_flexible,
            original_duration_minutes=t.original_duration_minutes,
            adjusted_duration_minutes=t.adjusted_duration_minutes,
            status=t.status,
        )
        for t in request.tasks
    ]

    plan, notification = service.rebalance_schedule_and_care(
        tasks=tasks,
        user_id=request.user_id,
        force_notify=request.force_notify,
    )

    notif_dto = _to_care_dto(notification) if notification else None
    return RebalanceScheduleResponse(
        plan_id=plan.plan_id,
        user_id=plan.user_id,
        created_at=plan.created_at,
        fatigue_level=plan.fatigue_level.value,
        load_reduction_ratio=plan.load_reduction_ratio,
        tasks_modified=[_to_task_dto(t) for t in plan.tasks_modified],
        summary=plan.summary,
        care_notification=notif_dto,
    )


@router.get("/care-notifications", response_model=CareNotificationListResponse)
def list_care_notifications(
    user_id: str = "default_user",
    unread_only: bool = False,
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> CareNotificationListResponse:
    """Retrieve history of proactive care notifications."""
    notifs = service.list_care_notifications(user_id=user_id, unread_only=unread_only)
    return CareNotificationListResponse(
        total_count=len(notifs),
        notifications=[_to_care_dto(n) for n in notifs],
    )


@router.post("/care-notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    service: ProactiveCareRebalancingService = Depends(get_proactive_care_service),
) -> dict[str, bool | str]:
    """Mark a proactive care notification as read."""
    success = service.mark_notification_read(notification_id=notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": True, "notification_id": notification_id}
