"""Read side of the ima card: aggregate status and the per-item report.

[INPUT]
- .ledger / .state / .credentials (POS: counts, run state, stored credentials)
- .job::find_job (POS: cron job state)

[OUTPUT]
- build_status / list_items

[POS]
Counts and phases only. The report exposes reason codes, never raw error text, so the UI owns all wording.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.cron.types import JobStatus

from app.database.connection import get_session
from app.services.wiki.agent_scope import normalize_agent_scope

from .credentials import load_credentials, mask_client_id
from .identity import NOTES_LANE
from .job import find_job
from .ledger import ATTENTION_STATUSES, ImaLedger, LedgerRow, LedgerStatus
from .models import MEDIA_LABELS
from .schemas import ImaItemCounts, ImaItemView, ImaJobStatus, ImaStatus
from .state import load_ima_config, load_ima_state

type ItemBucket = Literal["attention", "lossy", "remote_deleted"]

_REPORT_LIMIT = 200


async def build_status(agent_id: str | None) -> ImaStatus:
    credentials = await load_credentials()
    ledger = ImaLedger(normalize_agent_scope(agent_id))
    async with get_session() as db:
        config = await load_ima_config(db, agent_id=agent_id)
        state = await load_ima_state(db, agent_id=agent_id)
        counts = await ledger.counts(db)
    job = await find_job(agent_id)
    return ImaStatus(
        connected=credentials is not None,
        account_hint=mask_client_id(credentials.client_id) if credentials else "",
        needs_reauth=state.needs_reauth,
        knowledge_bases=config.knowledge_bases,
        include_notes=config.include_notes,
        job=ImaJobStatus(
            state="none" if job is None else ("paused" if job.status == JobStatus.PAUSED else "active"),
            next_run_at=job.next_run_at if job is not None else None,
        ),
        phase=state.phase,
        backfill_complete=state.backfill_complete,
        last_run_at=state.last_run_at,
        last_error_kind=state.last_error_kind,
        notes_unavailable=NOTES_LANE in state.failed_containers,
        counts=ImaItemCounts(
            total=counts.total,
            synced=counts.of(LedgerStatus.SYNCED),
            pending=counts.of(LedgerStatus.PENDING),
            failed=counts.of(LedgerStatus.FAILED),
            unsupported=counts.of(LedgerStatus.UNSUPPORTED),
            too_large=counts.of(LedgerStatus.TOO_LARGE),
            blocked=counts.of(LedgerStatus.BLOCKED),
            dismissed=counts.of(LedgerStatus.DISMISSED),
            remote_deleted=counts.of(LedgerStatus.REMOTE_DELETED),
            duplicate=counts.of(LedgerStatus.DUPLICATE),
            partial=counts.partial,
        ),
        total_chars=counts.total_chars,
    )


def _to_view(row: LedgerRow) -> ImaItemView:
    return ImaItemView(
        title=row.title,
        folder_path=row.folder_path,
        container_name=row.container_name,
        media_kind=MEDIA_LABELS.get(row.media_type, "") if row.media_type is not None else "",
        status=row.status,
        reason=row.error_kind,
        notes=list(row.fidelity_notes),
    )


async def list_items(agent_id: str | None, bucket: ItemBucket) -> list[ImaItemView]:
    ledger = ImaLedger(normalize_agent_scope(agent_id))
    async with get_session() as db:
        match bucket:
            case "attention":
                rows = await ledger.list_rows(db, statuses=ATTENTION_STATUSES, limit=_REPORT_LIMIT)
            case "lossy":
                rows = await ledger.list_rows(db, partial_only=True, limit=_REPORT_LIMIT)
            case "remote_deleted":
                rows = await ledger.list_rows(db, statuses=(LedgerStatus.REMOTE_DELETED,), limit=_REPORT_LIMIT)
    return [_to_view(row) for row in rows]
