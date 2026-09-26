"""Nightly review orchestration: score, watch, verify, digest.

[INPUT]
- experience_ledger list/record APIs (POS: shared event ledger)
- scorer.score_day (POS: rules-only collaboration signal)
- acceptance.open_watch/verify_watch (POS: no-recurrence bookkeeping)
- curator diagnostics + remediate APIs (POS: existing fix path, called not owned)

[OUTPUT]
- run_nightly_review: one full nightly pass returning NightlyReport
- start/stop_nightly_review_task: background loop lifecycle (mirrors curator)

[POS]
Thin nightly driver. Reads yesterday, writes findings/watches/digest, publishes
one morning notification. Never sweeps curator itself, never mutates skills.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 24
VERIFY_WINDOW_HOURS = 24
MIN_FINDING_COUNT = 3
QUIET_START_HOUR = 2
QUIET_END_HOUR = 5

_NEGATIVE_TYPES = (
    "review.rejected",
    "evolution.rejected",
    "evolution.apply_failed",
    "skill_growth.rejected",
    "skill_growth.blocked",
    "skill_growth.failed_scan",
)


@dataclass(slots=True)
class NightlyReport:
    """Outcome of one nightly pass, also used for the morning digest."""

    ran_at: datetime
    events_scanned: int
    findings_count: int
    watches_opened: int
    watches_verified: int
    finding_summaries: list[str] = field(default_factory=list)


def _in_quiet_hours(now: datetime) -> bool:
    local_hour = now.astimezone().hour
    return QUIET_START_HOUR <= local_hour < QUIET_END_HOUR


async def run_nightly_review(*, now: datetime | None = None) -> NightlyReport:
    """Run one full pass: score yesterday, open watches, verify due ones."""
    from app.services.skills.nightly_review.acceptance import open_watch
    from app.services.skills.nightly_review.scorer import score_day

    from ..experience_ledger import (
        list_experience_events,
    )

    current = now or datetime.now(UTC)
    since = current - timedelta(hours=LOOKBACK_HOURS)
    recent = await list_experience_events(limit=2000, event_types=_NEGATIVE_TYPES, since=since)
    events = [
        {
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "summary": event.summary,
        }
        for event in recent
    ]
    findings = score_day(events, min_count=MIN_FINDING_COUNT)

    watches_opened = 0
    summaries: list[str] = []
    for finding in findings:
        summary = f"{finding.entity_id}：{finding.count}次{finding.category}"
        summaries.append(summary)
        await open_watch(
            entity_type=finding.entity_type,
            entity_id=finding.entity_id,
            summary=summary,
        )
        watches_opened += 1

    watches_verified = await _verify_due_watches(current)

    report = NightlyReport(
        ran_at=current,
        events_scanned=len(events),
        findings_count=len(findings),
        watches_opened=watches_opened,
        watches_verified=watches_verified,
        finding_summaries=summaries,
    )
    await _publish_digest(report)
    await _record_digest_ledger(report)
    return report


async def _verify_due_watches(current: datetime) -> int:
    """Verify watches old enough to judge; returns verified count."""
    from app.services.skills.nightly_review.acceptance import (
        WATCH_OUTCOME_OPEN,
        RegressionWatch,
        verify_watch,
    )

    from ..experience_ledger import list_experience_events

    opened = await list_experience_events(
        limit=200,
        event_type="review.approved",
        entity_type="review",
        since=current - timedelta(hours=VERIFY_WINDOW_HOURS * 2),
    )
    verified = 0
    for event in opened:
        if event.outcome != WATCH_OUTCOME_OPEN:
            continue
        detail = event.detail or {}
        watch = RegressionWatch(
            watch_id=event.entity_id,
            entity_type=str(detail.get("entity_type") or "unknown"),
            entity_id=str(detail.get("entity_id") or "unknown"),
            opened_at=event.created_at,
        )
        try:
            if await verify_watch(watch, min_window_hours=VERIFY_WINDOW_HOURS, now=current):
                verified += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NightlyReview] Watch verify skipped: %s", exc)
    return verified


async def _publish_digest(report: NightlyReport) -> None:
    """Persist + broadcast the morning digest (existing notification path)."""
    from app.database.connection import get_session
    from app.database.models.notification import SystemNotification
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    if report.findings_count:
        lines = "；".join(report.finding_summaries[:5])
        message = f"发现{report.findings_count}个协作问题，已建{report.watches_opened}个不再犯跟踪：{lines}"
    else:
        message = "昨夜一切正常，无协作问题，无需处理"
    if report.watches_verified:
        message += f"；另有{report.watches_verified}个旧问题确认不再犯"
    title = "夜间体检报告"
    try:
        async with get_session() as session:
            session.add(
                SystemNotification(
                    id=uuid.uuid4().hex,
                    title=title,
                    message=message,
                    type="info",
                    source="nightly-review",
                    meta_data={
                        "findings_count": report.findings_count,
                        "watches_opened": report.watches_opened,
                        "watches_verified": report.watches_verified,
                    },
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NightlyReview] Digest persist skipped: %s", exc)
    try:
        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SYSTEM_NOTIFICATION,
                data={
                    "title": title,
                    "message": message,
                    "type": "info",
                    "meta_data": {
                        "source": "nightly-review",
                        "findings_count": report.findings_count,
                    },
                },
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NightlyReview] Digest publish skipped: %s", exc)


async def _record_digest_ledger(report: NightlyReport) -> None:
    """Mirror the digest into the ledger so dashboards can read it back."""
    from ..experience_ledger import (
        ExperienceEntityType,
        ExperienceEventType,
        ExperienceLedgerWrite,
        record_experience_event,
    )

    try:
        await record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_APPROVED.value,
                entity_type=ExperienceEntityType.REVIEW.value,
                entity_id=f"nightly-digest-{report.ran_at.strftime('%Y%m%d')}",
                lineage_id=f"nightly-digest-{report.ran_at.strftime('%Y%m%d')}",
                summary=(
                    f"夜间体检：扫描{report.events_scanned}条，发现"
                    f"{report.findings_count}个问题，验证通过{report.watches_verified}个"
                ),
                namespace="nightly-review",
                outcome="digest",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NightlyReview] Digest ledger mirror skipped: %s", exc)


_background_task: asyncio.Task[None] | None = None


async def _nightly_loop() -> None:
    """Background loop: one pass per day inside quiet hours."""
    while True:
        try:
            current = datetime.now(UTC)
            if _in_quiet_hours(current):
                report = await run_nightly_review(now=current)
                logger.info(
                    "[NightlyReview] Pass done: %d findings, %d verified",
                    report.findings_count,
                    report.watches_verified,
                )
                await asyncio.sleep(20 * 3600)
            else:
                await asyncio.sleep(1800)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NightlyReview] Pass failed: %s", exc)
            await asyncio.sleep(3600)


def start_nightly_review_task() -> None:
    """Start the nightly loop (call at warmup, mirrors curator)."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        return
    _background_task = asyncio.create_task(_nightly_loop())


def stop_nightly_review_task() -> None:
    """Stop the nightly loop (call at shutdown)."""
    global _background_task
    if _background_task is not None:
        _background_task.cancel()
        _background_task = None
