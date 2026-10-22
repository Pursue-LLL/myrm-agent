"""Pure Functional Multi-Surface Run Projection Service.

[INPUT]
- services.runs.projection.projection_types::RunStateSnapshot, AttemptRecord, etc.
- uuid, time, logging

[OUTPUT]
- RunProjectionService: Singleton managing run snapshots, monotonic events, and attempt telemetry
- run_projection_service: Global service instance

[POS]
app/services/runs/projection/run_projection_service.py: Implements MateClaw parity,
ensuring View = Project(RunState, Events) with attempt watermarks and fault traces.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Final

from app.services.runs.projection.projection_types import (
    AttemptRecord,
    AuditLedgerEntry,
    DeliverableItem,
    RunProjectionEvent,
    RunStateSnapshot,
    SurfaceViewType,
)

logger = logging.getLogger(__name__)


class RunProjectionService:
    """Core domain service for pure functional multi-surface run projections."""

    def __init__(self) -> None:
        self._snapshots: dict[str, RunStateSnapshot] = {}
        self._init_default_demo_run()

    def get_run_projection(self, run_id: str) -> RunStateSnapshot | None:
        """Fetch immutable RunStateSnapshot for pure functional rendering."""
        return self._snapshots.get(run_id)

    def get_run_events(self, run_id: str, since_timestamp_ms: int = 0) -> list[RunProjectionEvent]:
        """Fetch monotonic event stream since specified epoch watermark."""
        snapshot = self._snapshots.get(run_id)
        if snapshot is None:
            return []
        return [evt for evt in snapshot.events if evt.timestamp_ms >= since_timestamp_ms]

    def record_attempt(
        self,
        run_id: str,
        attempt_number: int,
        status: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_per_sec: float = 0.0,
        duration_ms: int | None = None,
        error_reason: str | None = None,
        stack_trace: str | None = None,
        diff_summary: str | None = None,
    ) -> AttemptRecord:
        """Append or update execution attempt telemetry."""
        snapshot = self._snapshots.get(run_id)
        now_ms = int(time.time() * 1000)
        attempt_id = f"att_{uuid.uuid4().hex[:10]}"

        record = AttemptRecord(
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_number=attempt_number,
            status=status,  # type: ignore[arg-type]
            started_at_ms=now_ms - (duration_ms or 0),
            finished_at_ms=now_ms if status in ("completed", "failed") else None,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_per_sec=tokens_per_sec,
            error_reason=error_reason,
            stack_trace=stack_trace,
            diff_summary=diff_summary,
        )

        if snapshot is not None:
            snapshot.attempts.append(record)
            snapshot.current_attempt = attempt_number
            snapshot.total_tokens += tokens_in + tokens_out
            if tokens_per_sec > 0:
                valid_rates = [att.tokens_per_sec for att in snapshot.attempts if att.tokens_per_sec > 0]
                snapshot.avg_tokens_per_sec = round(sum(valid_rates) / len(valid_rates), 2) if valid_rates else tokens_per_sec

            # Monotonic event logging
            self.append_event(
                run_id=run_id,
                event_type="attempt_state_transition",
                payload={
                    "attempt_id": attempt_id,
                    "attempt_number": attempt_number,
                    "status": status,
                    "duration_ms": duration_ms,
                    "tokens_per_sec": tokens_per_sec,
                },
            )

        return record

    def switch_surface(self, run_id: str, surface: SurfaceViewType) -> bool:
        """Update active projection surface viewport."""
        snapshot = self._snapshots.get(run_id)
        if snapshot is None:
            return False
        snapshot.active_surface = surface
        self.append_event(
            run_id=run_id,
            event_type="surface_switched",
            payload={"surface": surface},
        )
        return True

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> RunProjectionEvent | None:
        """Append monotonic event to run timeline."""
        snapshot = self._snapshots.get(run_id)
        if snapshot is None:
            return None

        event = RunProjectionEvent(
            event_id=f"evt_{uuid.uuid4().hex[:10]}",
            run_id=run_id,
            event_type=event_type,
            timestamp_ms=int(time.time() * 1000),
            payload=payload,
        )
        snapshot.events.append(event)
        return event

    def _init_default_demo_run(self) -> None:
        """Initialize MateClaw benchmark demonstration run."""
        run_id = "run_mateclaw_demo_001"
        now_ms = int(time.time() * 1000)

        attempt_1 = AttemptRecord(
            attempt_id="att_demo_01",
            run_id=run_id,
            attempt_number=1,
            status="failed",
            started_at_ms=now_ms - 12000,
            finished_at_ms=now_ms - 8500,
            duration_ms=3500,
            tokens_in=1420,
            tokens_out=210,
            tokens_per_sec=60.0,
            error_reason="ProviderRateLimitError: 429 Too Many Requests on primary endpoint",
            stack_trace="Traceback (most recent call last):\n  File 'harness/agent.py', line 142\nRateLimitError: 429",
            diff_summary="0 files mutated",
        )

        attempt_2 = AttemptRecord(
            attempt_id="att_demo_02",
            run_id=run_id,
            attempt_number=2,
            status="completed",
            started_at_ms=now_ms - 8000,
            finished_at_ms=now_ms - 1500,
            duration_ms=6500,
            tokens_in=2890,
            tokens_out=1450,
            tokens_per_sec=223.1,
            error_reason=None,
            stack_trace=None,
            diff_summary="3 files mutated (+128, -14 lines)",
        )

        deliverable = DeliverableItem(
            deliverable_id="deliv_01",
            title="Async Event Stream Projection Engine",
            type="source_code",
            path_or_uri="src/components/features/runtime/useRunProjection.ts",
            status="verified",
            created_at_ms=now_ms - 1500,
        )

        audit_entry = AuditLedgerEntry(
            audit_id="audit_01",
            action="file_mutation",
            actor="myrm_agent_runtime",
            risk_level="low",
            decision="approved",
            timestamp_ms=now_ms - 3000,
        )

        events: list[RunProjectionEvent] = [
            RunProjectionEvent(
                event_id="evt_01",
                run_id=run_id,
                event_type="run_initialized",
                timestamp_ms=now_ms - 12000,
                payload={"title": "Enterprise Microservice State Projection Refactor"},
            ),
            RunProjectionEvent(
                event_id="evt_02",
                run_id=run_id,
                event_type="attempt_failed",
                timestamp_ms=now_ms - 8500,
                payload={"attempt_number": 1, "reason": "429 RateLimit"},
            ),
            RunProjectionEvent(
                event_id="evt_03",
                run_id=run_id,
                event_type="attempt_retrying",
                timestamp_ms=now_ms - 8000,
                payload={"attempt_number": 2, "backoff_ms": 500},
            ),
            RunProjectionEvent(
                event_id="evt_04",
                run_id=run_id,
                event_type="attempt_completed",
                timestamp_ms=now_ms - 1500,
                payload={"attempt_number": 2, "tokens": 4340},
            ),
        ]

        self._snapshots[run_id] = RunStateSnapshot(
            run_id=run_id,
            title="Enterprise Microservice State Projection Refactor",
            status="completed",
            active_surface="runtime_console",
            current_attempt=2,
            attempts=[attempt_1, attempt_2],
            deliverables=[deliverable],
            audit_entries=[audit_entry],
            events=events,
            total_tokens=5970,
            avg_tokens_per_sec=141.55,
        )


# Global singleton instance
run_projection_service: Final[RunProjectionService] = RunProjectionService()
