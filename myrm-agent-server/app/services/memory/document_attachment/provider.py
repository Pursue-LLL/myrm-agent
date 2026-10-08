"""Service provider for Document Attachment Ownership & Reclaim Sweeps.

[POS]
Maintains singleton DocumentAttachmentSuite instance and bridges Harness execution
with Server DTO schemas.

[INPUT]
- myrm_agent_harness.toolkits.memory (DocumentAttachmentSuite, AttachmentOwnershipItem,
  MigrationLegacyEntry, MigrationReport, ReclaimAuditReport, AttachmentStats)
- app.schemas.document_attachment

[OUTPUT]
- get_document_attachment_suite, reset_document_attachment_suite
- execute_attach, query_document_attachments, query_attachment, execute_detach
- execute_remove_document, execute_sweep, execute_migrate, get_attachment_stats
"""

from __future__ import annotations

import base64

from myrm_agent_harness.toolkits.memory import (
    AttachmentOwnershipItem,
    AttachmentStats,
    DocumentAttachmentSuite,
    MigrationLegacyEntry,
    MigrationReport,
    ReclaimAuditReport,
)

from app.schemas.document_attachment import (
    AttachmentOwnershipItemDTO,
    AttachmentStatsDTO,
    AttachRequestDTO,
    DetachRequestDTO,
    DetachResponseDTO,
    MigrateRequestDTO,
    MigrationReportDTO,
    ReclaimAuditReportDTO,
)

_SUITE_INSTANCE: DocumentAttachmentSuite | None = None


def get_document_attachment_suite() -> DocumentAttachmentSuite:
    """Retrieve or initialize singleton DocumentAttachmentSuite."""
    global _SUITE_INSTANCE
    if _SUITE_INSTANCE is None:
        _SUITE_INSTANCE = DocumentAttachmentSuite()
    return _SUITE_INSTANCE


def reset_document_attachment_suite() -> None:
    """Reset singleton instance for testing isolation."""
    global _SUITE_INSTANCE
    _SUITE_INSTANCE = None


def _to_item_dto(item: AttachmentOwnershipItem) -> AttachmentOwnershipItemDTO:
    return AttachmentOwnershipItemDTO(
        attachment_id=item.attachment_id,
        document_id=item.document_id,
        attachment_hash=item.attachment_hash,
        storage_key=item.storage_key,
        file_name=item.file_name,
        mime_type=item.mime_type,
        byte_size=item.byte_size,
        created_at=item.created_at,
    )


def execute_attach(req: AttachRequestDTO) -> AttachmentOwnershipItemDTO:
    """Attaches content to a document, updating ownership and shared blob ref count."""
    suite = get_document_attachment_suite()
    content: bytes
    if req.content_base64 is not None:
        content = base64.b64decode(req.content_base64)
    elif req.content_text is not None:
        content = req.content_text.encode("utf-8")
    else:
        content = b""

    item = suite.attach(
        document_id=req.document_id,
        file_name=req.file_name,
        mime_type=req.mime_type,
        content=content,
    )
    return _to_item_dto(item)


def query_document_attachments(document_id: str) -> list[AttachmentOwnershipItemDTO]:
    """Retrieves all attachment items owned by a document."""
    suite = get_document_attachment_suite()
    items = suite.get_document_attachments(document_id=document_id)
    return [_to_item_dto(item) for item in items]


def query_attachment(
    document_id: str,
    attachment_id: str,
) -> AttachmentOwnershipItemDTO | None:
    """Retrieves an attachment metadata record if owned by the specified document."""
    suite = get_document_attachment_suite()
    item = suite.get_attachment(
        document_id=document_id,
        attachment_id=attachment_id,
    )
    if item is None:
        return None
    return _to_item_dto(item)


def execute_detach(req: DetachRequestDTO) -> DetachResponseDTO:
    """Detaches an attachment from a document and decrements the blob ref count."""
    suite = get_document_attachment_suite()
    success = suite.detach(
        document_id=req.document_id,
        attachment_id=req.attachment_id,
    )
    return DetachResponseDTO(
        success=success,
        document_id=req.document_id,
        attachment_id=req.attachment_id,
    )


def execute_remove_document(document_id: str) -> int:
    """Removes all attachments belonging to a document and decrements blob ref counts."""
    suite = get_document_attachment_suite()
    return suite.remove_document(document_id=document_id)


def execute_sweep() -> ReclaimAuditReportDTO:
    """Executes a deterministic sweep to unlink and purge unreferenced storage blobs."""
    suite = get_document_attachment_suite()
    report: ReclaimAuditReport = suite.sweep()
    return ReclaimAuditReportDTO(
        scanned_blobs=report.scanned_blobs,
        reclaimed_blobs=report.reclaimed_blobs,
        freed_bytes=report.freed_bytes,
        retained_blobs=report.retained_blobs,
        reclaimed_storage_keys=list(report.reclaimed_storage_keys),
        elapsed_ms=report.elapsed_ms,
    )


def execute_migrate(req: MigrateRequestDTO) -> MigrationReportDTO:
    """Flattens legacy multi-associated entries and drops orphaned unlinked blobs."""
    suite = get_document_attachment_suite()
    legacy_models: list[MigrationLegacyEntry] = [
        MigrationLegacyEntry(
            legacy_id=entry.legacy_id,
            attachment_hash=entry.attachment_hash,
            file_name=entry.file_name,
            mime_type=entry.mime_type,
            byte_size=entry.byte_size,
            associated_document_ids=tuple(entry.associated_document_ids),
        )
        for entry in req.legacy_entries
    ]

    decoded_payloads: dict[str, bytes] = {
        h: base64.b64decode(b64) for h, b64 in req.blob_payloads_base64.items()
    }

    report: MigrationReport = suite.migrate(
        legacy_entries=legacy_models,
        blob_payloads=decoded_payloads,
    )
    return MigrationReportDTO(
        total_scanned=report.total_scanned,
        migrated_records=report.migrated_records,
        dropped_orphans=report.dropped_orphans,
        elapsed_ms=report.elapsed_ms,
    )


def get_attachment_stats() -> AttachmentStatsDTO:
    """Computes current attachment, document, and physical blob statistics."""
    suite = get_document_attachment_suite()
    stats: AttachmentStats = suite.get_stats()
    return AttachmentStatsDTO(
        total_documents=stats.total_documents,
        total_attachment_rows=stats.total_attachment_rows,
        total_storage_keys=stats.total_storage_keys,
        total_physical_bytes=stats.total_physical_bytes,
        orphaned_unclaimed_keys=stats.orphaned_unclaimed_keys,
    )
