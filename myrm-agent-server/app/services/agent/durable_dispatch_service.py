"""[INPUT] WorkContractDTO, EvidenceSubmitRequest, and policy mapping parameters.
[OUTPUT] DispatchReceiptDTO, PrestartRevalidateResponse, EvidenceSubmitResponse, and RecoveryPlanDTO.
[POS] Service layer managing durable remote dispatch engines and journals per chat session.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.durable_dispatch import (
    DurableRemoteDispatchEngine,
    EvidenceItem,
    WorkContract,
)

from app.schemas.durable_dispatch import (
    DispatchReceiptDTO,
    EvidenceSubmitRequest,
    EvidenceSubmitResponse,
    JournalEntryDTO,
    PrestartRevalidateResponse,
    RecoveryPlanDTO,
    WorkContractDTO,
)

logger = logging.getLogger(__name__)


class DurableDispatchService:
    """Service layer managing remote dispatch transactions and durable journals."""

    def __init__(self) -> None:
        self._engines: Dict[str, DurableRemoteDispatchEngine] = {}

    def _get_engine(self, chat_id: str) -> DurableRemoteDispatchEngine:
        if chat_id not in self._engines:
            self._engines[chat_id] = DurableRemoteDispatchEngine()
        return self._engines[chat_id]

    def prepare_dispatch(
        self,
        chat_id: str,
        contract_dto: WorkContractDTO,
        principal_token: str = "valid_coordinator_token",
    ) -> DispatchReceiptDTO:
        """Register a work contract and record initial dispatch journal entry."""
        engine = self._get_engine(chat_id)
        contract = WorkContract(
            dispatch_id=contract_dto.dispatch_id,
            task_name=contract_dto.task_name,
            target_peer_id=contract_dto.target_peer_id,
            coordinator_principal_id=contract_dto.coordinator_principal_id,
            max_budget_tokens=contract_dto.max_budget_tokens,
            expires_at=contract_dto.expires_at,
            required_policies=contract_dto.required_policies,
        )
        receipt = engine.prepare_dispatch(contract=contract, principal_token=principal_token)
        return DispatchReceiptDTO(
            dispatch_id=receipt.dispatch_id,
            acknowledged_seq=receipt.acknowledged_seq,
            prestart_verified=receipt.prestart_verified,
            peer_status=receipt.peer_status,
        )

    def revalidate_pre_start_policy(
        self,
        chat_id: str,
        dispatch_id: str,
        active_policies: Dict[str, bool],
    ) -> PrestartRevalidateResponse:
        """Revalidate security policies in a fail-closed gate prior to remote start."""
        engine = self._get_engine(chat_id)
        passed = engine.revalidate_pre_start_policy(dispatch_id, active_policies)
        contract = engine.get_contract(dispatch_id)
        count = len(contract.required_policies) if contract else len(active_policies)
        return PrestartRevalidateResponse(
            dispatch_id=dispatch_id,
            passed=passed,
            checked_policies_count=count,
        )

    def submit_evidence(
        self,
        chat_id: str,
        dispatch_id: str,
        req: EvidenceSubmitRequest,
    ) -> EvidenceSubmitResponse:
        """Admit structured evidence under strict bounded limits."""
        engine = self._get_engine(chat_id)
        evidence_id = f"evi_{uuid.uuid4().hex[:8]}"
        item = EvidenceItem(
            evidence_id=evidence_id,
            evidence_type=req.evidence_type,
            size_bytes=req.size_bytes,
            content_digest=req.content_digest,
            description=req.description,
        )
        admitted = engine.admit_evidence(dispatch_id, item)
        return EvidenceSubmitResponse(
            evidence_id=evidence_id,
            dispatch_id=dispatch_id,
            admitted=admitted,
            size_bytes=req.size_bytes,
        )

    def get_journal(self, chat_id: str, dispatch_id: str) -> List[JournalEntryDTO]:
        """Fetch all append-only journal entries for a dispatch transaction."""
        engine = self._get_engine(chat_id)
        entries = engine.journal.get_journal(dispatch_id)
        return [
            JournalEntryDTO(
                journal_id=e.journal_id,
                dispatch_id=e.dispatch_id,
                seq=e.seq,
                entry_type=e.entry_type.value,
                timestamp=e.timestamp,
                payload_hash=e.payload_hash,
                metadata=e.metadata,
            )
            for e in entries
        ]

    def compute_recovery_plan(self, chat_id: str, dispatch_id: str) -> RecoveryPlanDTO:
        """Compute an idempotent crash recovery plan based on current journal state."""
        engine = self._get_engine(chat_id)
        plan = engine.compute_recovery_plan(dispatch_id)
        return RecoveryPlanDTO(
            dispatch_id=plan.dispatch_id,
            last_known_seq=plan.last_known_seq,
            last_entry_type=plan.last_entry_type.value,
            can_resume=plan.can_resume,
            resume_action=plan.resume_action,
        )


_instance: Optional[DurableDispatchService] = None


def get_durable_dispatch_service() -> DurableDispatchService:
    """Singleton getter for DurableDispatchService."""
    global _instance
    if _instance is None:
        _instance = DurableDispatchService()
    return _instance
