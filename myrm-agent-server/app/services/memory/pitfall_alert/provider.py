"""Service provider for proactive pitfall alert and decision assist engine.

[POS]
Maintains singleton instance of ProactivePitfallAlertEngine, exposes high-level
evaluation, session muting, and historical postmortem registration methods.

[INPUT]
- typing, logging
- myrm_agent_harness.toolkits.memory (AlertSeverity, DispatchChannel, PastPitfallRetriever,
  PitfallAlertCard, PitfallEvaluationReport, PitfallTriadRecord, ProactivePitfallAlertEngine,
  ShadowDecisionIntentRecognizer)
- app.schemas.pitfall_alert (EvaluateInputRequest, MuteSubjectRequest, PitfallAlertCardDTO,
  PitfallAlertStatusResponse, PitfallEvaluationResponse, SeedTriadRequest, UnmuteSubjectRequest)

[OUTPUT]
- PitfallAlertServiceProvider, get_pitfall_alert_service
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.toolkits.memory import (
    AlertSeverity,
    PastPitfallRetriever,
    ProactivePitfallAlertEngine,
    ShadowDecisionIntentRecognizer,
)

from app.schemas.pitfall_alert import (
    EvaluateInputRequest,
    PitfallAlertCardDTO,
    PitfallAlertStatusResponse,
    PitfallEvaluationResponse,
    SeedTriadRequest,
)

logger = logging.getLogger(__name__)


class PitfallAlertServiceProvider:
    """Manages the lifecycle and business logic of the proactive pitfall alert engine."""

    _instance: ClassVar[PitfallAlertServiceProvider | None] = None

    def __init__(self) -> None:
        self._retriever = PastPitfallRetriever()
        self._recognizer = ShadowDecisionIntentRecognizer()
        self._engine = ProactivePitfallAlertEngine(
            intent_recognizer=self._recognizer,
            retriever=self._retriever,
        )
        self._bootstrap_seeded_postmortems()

    def _bootstrap_seeded_postmortems(self) -> None:
        """Seed baseline engineering postmortems for immediate proactive protection."""
        default_triads = [
            PastPitfallRetriever.create_triad(
                subject="redis",
                approach="无自动续期的分布式锁",
                pitfall_lesson="业务偶发长尾 GC 导致锁过期被并发抢占，造成并发写脏数据与死锁雪崩故障",
                validated_alternative="使用 Redlock 看门狗自动续期机制，或切换至数据库行级乐观锁 CAS",
                severity=AlertSeverity.CRITICAL,
                incident_date="2025-04-12",
                version_context="Redis 6.2",
            ),
            PastPitfallRetriever.create_triad(
                subject="mongodb",
                approach="单节点或无强一致写入配置",
                pitfall_lesson="分片网络分区时因 w:1 写入确认导致丢失数据与幻读事故",
                validated_alternative="采用 w:majority 与 readConcern:majority，或直接选用 PostgreSQL 强一致性事务",
                severity=AlertSeverity.CRITICAL,
                incident_date="2024-11-08",
                version_context="MongoDB 5.0",
            ),
            PastPitfallRetriever.create_triad(
                subject="celery",
                approach="默认 prefetch_multiplier 配置处理耗时任务",
                pitfall_lesson="长耗时任务被单个 worker 贪婪预取堆积，导致其他 worker 饥饿与队列超时雪崩",
                validated_alternative="设置 worker_prefetch_multiplier=1 并启用 acks_late 保证均衡消费",
                severity=AlertSeverity.WARNING,
                incident_date="2025-01-20",
                version_context="Celery 5.3",
            ),
        ]
        self._retriever.seed_records(default_triads)
        logger.info(
            "Bootstrapped %d default postmortem lessons into PitfallAlertServiceProvider",
            len(default_triads),
        )

    async def evaluate_query(
        self, request: EvaluateInputRequest
    ) -> PitfallEvaluationResponse:
        """Evaluate user message against historical postmortems and return alert response."""
        card, report = await self._engine.evaluate_input(
            user_input=request.user_input,
            session_id=request.session_id,
            current_runtime_version=request.current_runtime_version,
        )

        card_dto: PitfallAlertCardDTO | None = None
        if card is not None:
            card_dto = PitfallAlertCardDTO(
                alert_id=card.alert_id,
                subject=card.subject,
                intent_summary=card.intent_summary,
                historical_pitfall=card.historical_pitfall,
                recommended_action=card.recommended_action,
                severity=card.severity.value,
                source_ref=card.source_ref,
                drift_warning=card.drift_warning,
                dispatch_channel=card.dispatch_channel.value,
                is_muted=card.is_muted,
            )

        return PitfallEvaluationResponse(
            evaluation_id=report.evaluation_id,
            intent_detected=report.intent_detected,
            intent_level=report.intent_level,
            triad_matched=report.triad_matched,
            alert_generated=report.alert_generated,
            dispatched_channel=report.dispatched_channel,
            latency_ms=report.latency_ms,
            alert_card=card_dto,
        )

    def register_triad(self, request: SeedTriadRequest) -> None:
        """Register a new causal triad into the in-memory retriever."""
        severity_enum = (
            AlertSeverity.CRITICAL
            if request.severity == "critical"
            else (
                AlertSeverity.INFO
                if request.severity == "info"
                else AlertSeverity.WARNING
            )
        )
        record = PastPitfallRetriever.create_triad(
            subject=request.subject,
            approach=request.approach,
            pitfall_lesson=request.pitfall_lesson,
            validated_alternative=request.validated_alternative,
            severity=severity_enum,
            incident_date=request.incident_date,
            version_context=request.version_context,
            source_id="api_seed",
        )
        self._retriever.seed_records([record])

    def mute_subject(self, session_id: str, subject: str) -> None:
        """Mute future alerts for given technical subject within the session."""
        self._engine.mute_subject(session_id=session_id, subject=subject)

    def unmute_subject(self, session_id: str, subject: str) -> None:
        """Unmute previously suppressed alerts for given technical subject."""
        self._engine.unmute_subject(session_id=session_id, subject=subject)

    def get_status(self) -> PitfallAlertStatusResponse:
        """Report operational status and configuration counters."""
        seeded_count = len(self._retriever._in_memory_records)
        muted_count = len(self._engine._muted_by_session)
        return PitfallAlertStatusResponse(
            active=True,
            seeded_triads_count=seeded_count,
            muted_sessions_count=muted_count,
        )


def get_pitfall_alert_service() -> PitfallAlertServiceProvider:
    """Return the global singleton instance of PitfallAlertServiceProvider."""
    if PitfallAlertServiceProvider._instance is None:
        PitfallAlertServiceProvider._instance = PitfallAlertServiceProvider()
    return PitfallAlertServiceProvider._instance
