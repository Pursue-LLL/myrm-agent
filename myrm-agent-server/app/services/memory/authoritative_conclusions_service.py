# [POS]: app/services/memory/authoritative_conclusions_service.py
# [INPUT]: app.schemas.authoritative_conclusions, myrm_agent_harness.toolkits.memory
# [OUTPUT]: AuthoritativeConclusionsService, get_authoritative_conclusions_service

"""Business service implementing Explicit Authoritative Conclusions and Audit Tooling Suite (Item 111)."""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    AuthoritativeConclusion,
    AuthoritativeConclusionStore,
    ConclusionAnchorProjection,
    ConclusionAuditRecord,
    ConclusionContextAnchor,
    ConclusionStatus,
)

from app.schemas.authoritative_conclusions import (
    AuthoritativeConclusionDTO,
    ConclusionAnchorProjectionDTO,
    ConclusionAuditRecordDTO,
    DeleteConclusionRequest,
    DeprecateConclusionRequest,
    WriteConclusionRequest,
)

logger = logging.getLogger(__name__)


def _conclusion_to_dto(conc: AuthoritativeConclusion) -> AuthoritativeConclusionDTO:
    """Map internal domain conclusion to API DTO."""
    return AuthoritativeConclusionDTO(
        conclusion_id=conc.conclusion_id,
        peer_id=conc.peer_id,
        content=conc.content,
        status=conc.status.value,
        scope_tag=conc.scope_tag,
        created_at=conc.created_at,
        confirmed_at=conc.confirmed_at,
        deprecated_at=conc.deprecated_at,
    )


def _audit_to_dto(audit: ConclusionAuditRecord) -> ConclusionAuditRecordDTO:
    """Map internal audit ledger record to API DTO."""
    return ConclusionAuditRecordDTO(
        audit_id=audit.audit_id,
        conclusion_id=audit.conclusion_id,
        action=audit.action.value,
        operator_peer_id=audit.operator_peer_id,
        previous_status=audit.previous_status.value if audit.previous_status else None,
        new_status=audit.new_status.value if audit.new_status else None,
        rationale=audit.rationale,
        timestamp=audit.timestamp,
    )


def _projection_to_dto(proj: ConclusionAnchorProjection) -> ConclusionAnchorProjectionDTO:
    """Map internal anchor projection to API DTO."""
    return ConclusionAnchorProjectionDTO(
        formatted_prompt_block=proj.formatted_prompt_block,
        total_active_conclusions=proj.total_active_conclusions,
        token_estimate=proj.token_estimate,
    )


class AuthoritativeConclusionsService:
    """Service managing authoritative conclusion lifecycle, queries, and audit trails."""

    def __init__(self) -> None:
        self._store = AuthoritativeConclusionStore()
        self._anchor = ConclusionContextAnchor()

    def write_conclusion(self, req: WriteConclusionRequest) -> AuthoritativeConclusionDTO:
        """Declare a new authoritative conclusion."""
        conc = self._store.write_conclusion(
            content=req.content,
            peer_id=req.peer_id,
            scope_tag=req.scope_tag,
            conclusion_id=req.conclusion_id,
            operator_peer_id=req.peer_id,
            auto_confirm=req.auto_confirm,
            rationale=req.rationale,
        )
        return _conclusion_to_dto(conc)

    def get_conclusion(self, conclusion_id: str) -> AuthoritativeConclusionDTO | None:
        """Retrieve a single conclusion by identifier."""
        conc = self._store.get_conclusion(conclusion_id)
        if conc is None:
            return None
        return _conclusion_to_dto(conc)

    def list_conclusions(
        self,
        peer_id: str | None = None,
        status_str: str | None = None,
        scope_tag: str | None = None,
        keyword: str | None = None,
    ) -> list[AuthoritativeConclusionDTO]:
        """List conclusions with multi-dimensional filtering."""
        status_enum: ConclusionStatus | None = None
        if status_str:
            try:
                status_enum = ConclusionStatus(status_str)
            except ValueError:
                status_enum = None

        concs = self._store.list_conclusions(
            peer_id=peer_id,
            status=status_enum,
            scope_tag=scope_tag,
            keyword=keyword,
        )
        return [_conclusion_to_dto(c) for c in concs]

    def deprecate_conclusion(
        self,
        conclusion_id: str,
        req: DeprecateConclusionRequest,
    ) -> AuthoritativeConclusionDTO | None:
        """Mark an active conclusion as deprecated with audit logging."""
        deprecated = self._store.deprecate_conclusion(
            conclusion_id=conclusion_id,
            operator_peer_id=req.operator_peer_id,
            rationale=req.rationale,
        )
        if deprecated is None:
            return None
        return _conclusion_to_dto(deprecated)

    def delete_conclusion(
        self,
        conclusion_id: str,
        req: DeleteConclusionRequest,
    ) -> bool:
        """Physically erase a conclusion for PII/policy compliance while logging deletion event."""
        return self._store.delete_conclusion(
            conclusion_id=conclusion_id,
            operator_peer_id=req.operator_peer_id,
            rationale=req.rationale,
        )

    def list_audits(self, conclusion_id: str | None = None) -> list[ConclusionAuditRecordDTO]:
        """Query conclusion audit history records."""
        audits = self._store.list_audits(conclusion_id=conclusion_id)
        return [_audit_to_dto(a) for a in audits]

    def get_anchor_projection(self) -> ConclusionAnchorProjectionDTO:
        """Render anti-dilution context anchor block from all active confirmed conclusions."""
        active_conclusions = self._store.list_conclusions(status=ConclusionStatus.CONFIRMED)
        proj = self._anchor.format_anchor_block(active_conclusions)
        return _projection_to_dto(proj)


@lru_cache(maxsize=1)
def get_authoritative_conclusions_service() -> AuthoritativeConclusionsService:
    """Dependency provider returning singleton AuthoritativeConclusionsService."""
    return AuthoritativeConclusionsService()
