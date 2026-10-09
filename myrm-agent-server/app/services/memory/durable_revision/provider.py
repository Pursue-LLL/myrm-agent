"""Service provider for Durable Revision & Concurrent Writes.

[POS]
Maintains singleton DurableRevisionSuite instance and bridges Harness execution
with Server DTO schemas.

[INPUT]
- myrm_agent_harness.toolkits.memory (DurableRevisionSuite, ChangeReceipt, WritePayload, SnapshotReadView)
- app.schemas.durable_revision

[OUTPUT]
- get_durable_revision_suite, reset_durable_revision_suite
- execute_durable_write, query_snapshot, query_receipt, execute_rollback, execute_retract, get_revision_stats
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    ChangeReceipt,
    DurableRevisionSuite,
    SnapshotReadView,
    WritePayload,
)

from app.schemas.durable_revision import (
    ChangeReceiptDTO,
    DurableRevisionStatsDTO,
    RetractRequestDTO,
    RollbackRequestDTO,
    SnapshotReadViewDTO,
    WritePayloadDTO,
)

_SUITE_INSTANCE: DurableRevisionSuite | None = None


def get_durable_revision_suite() -> DurableRevisionSuite:
    """Retrieve or initialize singleton DurableRevisionSuite."""
    global _SUITE_INSTANCE
    if _SUITE_INSTANCE is None:
        _SUITE_INSTANCE = DurableRevisionSuite()
    return _SUITE_INSTANCE


def reset_durable_revision_suite() -> None:
    """Reset singleton instance for testing isolation."""
    global _SUITE_INSTANCE
    _SUITE_INSTANCE = None


def _to_receipt_dto(rc: ChangeReceipt) -> ChangeReceiptDTO:
    return ChangeReceiptDTO(
        receipt_id=rc.receipt_id,
        key=rc.key,
        status=rc.status.value,
        canonical_revision=rc.canonical_revision,
        timestamp=rc.timestamp,
        pending_error=rc.pending_error,
        checksum_crc32=rc.checksum_crc32,
        metadata=dict(rc.metadata),
    )


def _to_snapshot_dto(snap: SnapshotReadView) -> SnapshotReadViewDTO:
    return SnapshotReadViewDTO(
        key=snap.key,
        revision=snap.revision,
        content=snap.content,
        tags=dict(snap.tags),
        is_tombstone=snap.is_tombstone,
        created_at=snap.created_at,
        checksum_crc32=snap.checksum_crc32,
    )


def execute_durable_write(req: WritePayloadDTO) -> ChangeReceiptDTO:
    """Execute a durable write mutation and return a typed change receipt."""
    suite = get_durable_revision_suite()
    payload = WritePayload(
        key=req.key,
        content=req.content,
        tags=req.tags,
        expected_revision=req.expected_revision,
        request_id=req.request_id or "",
    )
    rc = suite.write(payload)
    return _to_receipt_dto(rc)


def query_snapshot(key: str, revision: int | None = None) -> SnapshotReadViewDTO | None:
    """Query a point-in-time snapshot for a given key and revision."""
    suite = get_durable_revision_suite()
    snap = suite.read_snapshot(key=key, target_revision=revision)
    if not snap:
        return None
    return _to_snapshot_dto(snap)


def query_receipt(receipt_id: str) -> ChangeReceiptDTO | None:
    """Query an authoritative change receipt by ID."""
    suite = get_durable_revision_suite()
    rc = suite.get_receipt(receipt_id)
    if not rc:
        return None
    return _to_receipt_dto(rc)


def execute_rollback(req: RollbackRequestDTO) -> ChangeReceiptDTO:
    """Revert key to a historical revision."""
    suite = get_durable_revision_suite()
    rc = suite.rollback(key=req.key, target_revision=req.target_revision)
    return _to_receipt_dto(rc)


def execute_retract(req: RetractRequestDTO) -> ChangeReceiptDTO:
    """Mark a key as retracted with a tombstone revision."""
    suite = get_durable_revision_suite()
    rc = suite.retract(key=req.key)
    return _to_receipt_dto(rc)


def get_revision_stats() -> DurableRevisionStatsDTO:
    """Return operational metrics for durable revisions."""
    suite = get_durable_revision_suite()
    stats = suite.get_stats()
    return DurableRevisionStatsDTO(
        total_receipts=int(stats.get("total_receipts", 0)),
        applied_receipts=int(stats.get("applied_receipts", 0)),
        contention_receipts=int(stats.get("contention_receipts", 0)),
        validation_failed_receipts=int(stats.get("validation_failed_receipts", 0)),
        quarantined_receipts=int(stats.get("quarantined_receipts", 0)),
        superseded_receipts=int(stats.get("superseded_receipts", 0)),
        reverted_receipts=int(stats.get("reverted_receipts", 0)),
        failed_durable_receipts=int(stats.get("failed_durable_receipts", 0)),
        active_locks=int(stats.get("active_locks", 0)),
        total_snapshots=int(stats.get("total_snapshots", 0)),
    )
