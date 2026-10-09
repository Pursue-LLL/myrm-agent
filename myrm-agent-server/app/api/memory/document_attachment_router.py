"""REST API router for Document Attachment Ownership & Reclaim Sweeps.

[POS]
Provides HTTP endpoints for document-owned attachment binding, retrieval,
detachment, deterministic GC reclaim sweeps, and legacy migration.

[INPUT]
- fastapi
- app.schemas.document_attachment
- app.services.memory.document_attachment.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

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
from app.services.memory.document_attachment.provider import (
    execute_attach,
    execute_detach,
    execute_migrate,
    execute_remove_document,
    execute_sweep,
    get_attachment_stats,
    query_attachment,
    query_document_attachments,
)

router = APIRouter(prefix="/document-attachment", tags=["Document Attachment Ownership"])


@router.post(
    "/attach",
    response_model=AttachmentOwnershipItemDTO,
    status_code=status.HTTP_200_OK,
    summary="Attach file or blob to document",
)
def attach_file(req: AttachRequestDTO) -> AttachmentOwnershipItemDTO:
    """Attach content to a document, updating ownership record and blob ref count."""
    return execute_attach(req)


@router.get(
    "/document/{document_id}/attachments",
    response_model=list[AttachmentOwnershipItemDTO],
    status_code=status.HTTP_200_OK,
    summary="List all attachments owned by document",
)
def list_document_attachments(document_id: str) -> list[AttachmentOwnershipItemDTO]:
    """Retrieve all attachment items belonging to the document."""
    return query_document_attachments(document_id)


@router.get(
    "/document/{document_id}/attachment/{attachment_id}",
    response_model=AttachmentOwnershipItemDTO,
    status_code=status.HTTP_200_OK,
    summary="Get single attachment metadata",
)
def get_attachment(document_id: str, attachment_id: str) -> AttachmentOwnershipItemDTO:
    """Retrieve an attachment metadata record scoped to the document."""
    item = query_attachment(document_id=document_id, attachment_id=attachment_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attachment {attachment_id} not found on document {document_id}",
        )
    return item


@router.post(
    "/detach",
    response_model=DetachResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Detach attachment from document",
)
def detach_attachment(req: DetachRequestDTO) -> DetachResponseDTO:
    """Detach attachment record from document, decrementing blob ref count."""
    return execute_detach(req)


@router.delete(
    "/document/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove document and cascade detach all its attachments",
)
def remove_document_attachments(document_id: str) -> dict[str, int]:
    """Cascading detach all attachments owned by the document."""
    detached_count = execute_remove_document(document_id)
    return {"detached_count": detached_count}


@router.post(
    "/reclaim-sweep",
    response_model=ReclaimAuditReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute deterministic garbage collection sweep",
)
def trigger_reclaim_sweep() -> ReclaimAuditReportDTO:
    """Deterministic GC sweep to unlink and purge unreferenced blobs."""
    return execute_sweep()


@router.post(
    "/migrate",
    response_model=MigrationReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Migrate legacy associations to document-owned records",
)
def migrate_legacy_attachments(req: MigrateRequestDTO) -> MigrationReportDTO:
    """Flatten legacy multi-associated entries and drop hanging orphans."""
    return execute_migrate(req)


@router.get(
    "/stats",
    response_model=AttachmentStatsDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve attachment and storage statistics",
)
def get_stats() -> AttachmentStatsDTO:
    """Fetch current attachment lifecycle statistics."""
    return get_attachment_stats()
