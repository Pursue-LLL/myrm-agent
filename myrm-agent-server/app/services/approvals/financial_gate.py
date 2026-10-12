"""Mandatory Human Sign-Off Gate for Financial and Irreversible Outbound Actions.

[POS]
Enforces the industrial safety principle: agents may classify and draft,
but any action transferring funds, sending emails externally, or pushing webhooks
requires physical human sign-off with revealed action surfaces, before-run plans,
and post-execution delivery receipt binding (Decision-to-Receipt three-stage chain).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from uuid import uuid4

from app.schemas.local_action_audit import (
    ActionSurface,
    BeforeRunPlan,
    DeliveryReceipt,
    FinancialSignOffDraft,
)
from app.services.audit.egress_footprint_ledger import get_egress_footprint_ledger
from app.services.audit.local_action_ledger import get_local_action_ledger

logger = logging.getLogger(__name__)


class FinancialSignOffGateService:
    """Manages high-impact financial & outbound draft workflows, sign-offs, and receipts."""

    def __init__(self) -> None:
        self._drafts: dict[str, FinancialSignOffDraft] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def create_draft(
        self,
        agent_id: str,
        action_surface: ActionSurface,
        plan: BeforeRunPlan,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> FinancialSignOffDraft:
        """Create a new pending sign-off draft with validated action digest."""
        async with self._lock:
            draft_id = str(uuid4())
            draft = FinancialSignOffDraft(
                draft_id=draft_id,
                agent_id=agent_id,
                session_id=session_id,
                task_id=task_id,
                action_surface=action_surface,
                plan=plan,
                status="PENDING_SIGNOFF",
                created_at=time.time(),
            )
            self._drafts[draft_id] = draft

            # Record drafting access into tamper-evident local action ledger
            local_ledger = get_local_action_ledger()
            await local_ledger.record_access(
                agent_id=agent_id,
                target_entity_type="signoff_draft",
                target_entity_id=draft_id,
                entity_hash=action_surface.action_digest,
                action="draft_action_surface",
                intent_summary=f"Drafted {action_surface.action_type} awaiting physical human sign-off",
                operator_or_model=agent_id,
                session_id=session_id,
                task_id=task_id,
            )

            logger.info(
                "Created financial sign-off draft %s for action %s by agent %s",
                draft_id,
                action_surface.action_type,
                agent_id,
            )
            return draft

    def get_draft(self, draft_id: str) -> FinancialSignOffDraft | None:
        """Retrieve a sign-off draft by ID."""
        return self._drafts.get(draft_id)

    def list_drafts(
        self,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[FinancialSignOffDraft]:
        """List sign-off drafts matching optional filters in reverse chronological order."""
        res = list(self._drafts.values())
        if agent_id:
            res = [d for d in res if d.agent_id == agent_id]
        if status:
            res = [d for d in res if d.status == status]
        return sorted(res, key=lambda d: d.created_at, reverse=True)

    async def sign_off(
        self,
        draft_id: str,
        operator_id: str,
        decision: str,  # "APPROVE" | "REJECT"
        rejection_reason: str | None = None,
    ) -> FinancialSignOffDraft:
        """Process physical human sign-off decision on a draft."""
        async with self._lock:
            draft = self._drafts.get(draft_id)
            if not draft:
                raise ValueError(f"Draft {draft_id} not found")
            if draft.status != "PENDING_SIGNOFF":
                raise ValueError(f"Draft {draft_id} is in status {draft.status}, cannot sign-off")

            now = time.time()
            if decision == "APPROVE":
                # Generate verifiable sign-off token
                token_raw = f"{draft_id}:{operator_id}:{draft.action_surface.action_digest}:{now}".encode("utf-8")
                token = hashlib.sha256(token_raw).hexdigest()

                draft.status = "APPROVED"
                draft.operator_id = operator_id
                draft.signoff_token = token
                draft.signed_at = now

                logger.info("Human operator %s APPROVED financial draft %s", operator_id, draft_id)
            else:
                draft.status = "REJECTED"
                draft.operator_id = operator_id
                draft.signed_at = now
                logger.info(
                    "Human operator %s REJECTED financial draft %s: %s",
                    operator_id,
                    draft_id,
                    rejection_reason or "No reason",
                )

            # Record sign-off decision into local action ledger
            local_ledger = get_local_action_ledger()
            await local_ledger.record_access(
                agent_id=draft.agent_id,
                target_entity_type="signoff_draft",
                target_entity_id=draft_id,
                entity_hash=draft.action_surface.action_digest,
                action=f"signoff_{decision.lower()}",
                intent_summary=f"Human sign-off decision: {decision} by {operator_id}",
                operator_or_model=operator_id,
                session_id=draft.session_id,
                task_id=draft.task_id,
            )

            return draft

    async def bind_delivery_receipt(
        self,
        draft_id: str,
        external_reference_id: str | None,
        delivery_status: str,  # "DELIVERED" | "SETTLED" | "FAILED"
        response_data: str,
    ) -> DeliveryReceipt:
        """Bind post-execution delivery receipt to complete the Decision-to-Receipt chain."""
        async with self._lock:
            draft = self._drafts.get(draft_id)
            if not draft:
                raise ValueError(f"Draft {draft_id} not found")
            if draft.status != "APPROVED":
                raise ValueError(f"Cannot bind delivery receipt to draft in status {draft.status}")

            response_digest = hashlib.sha256(response_data.encode("utf-8")).hexdigest()
            receipt = DeliveryReceipt(
                delivery_receipt_id=str(uuid4()),
                approval_id=draft_id,
                action_type=draft.action_surface.action_type,
                external_reference_id=external_reference_id,
                delivery_status=delivery_status,  # type: ignore[arg-type]
                completed_at=time.time(),
                response_digest=response_digest,
            )
            draft.delivery_receipt = receipt
            draft.status = "EXECUTED" if delivery_status in ("DELIVERED", "SETTLED") else "APPROVED"

            # Record corresponding egress footprint
            egress_ledger = get_egress_footprint_ledger()
            target_host = "external-destination"
            target_url = "outbound://delivered"
            if draft.action_surface.endpoint_details:
                target_url = draft.action_surface.endpoint_details.target_url
                target_host = target_url.split("/")[2] if "//" in target_url else "webhook-endpoint"
            elif draft.action_surface.email_details:
                target_host = "smtp-gateway"
                target_url = f"mailto:{','.join(draft.action_surface.email_details.recipients)}"
            elif draft.action_surface.financial_details:
                target_host = "banking-payment-gateway"
                target_url = f"payment://{draft.action_surface.financial_details.payee_account}"

            await egress_ledger.record_egress(
                agent_id=draft.agent_id,
                target_host=target_host,
                target_url=target_url,
                content_summary=f"Delivered {draft.action_surface.action_type} ref={external_reference_id}",
                sensitivity_level="CRITICAL" if draft.action_surface.action_type == "payment_transfer" else "HIGH",
                taint_tags=["financial"] if draft.action_surface.action_type == "payment_transfer" else ["external"],
                approved_by_human=True,
                approval_id=draft_id,
                session_id=draft.session_id,
                task_id=draft.task_id,
            )

            logger.info("Bound delivery receipt %s to draft %s", receipt.delivery_receipt_id, draft_id)
            return receipt


_default_financial_gate: FinancialSignOffGateService | None = None


def get_financial_sign_off_gate() -> FinancialSignOffGateService:
    """Return the singleton instance of FinancialSignOffGateService."""
    global _default_financial_gate
    if _default_financial_gate is None:
        _default_financial_gate = FinancialSignOffGateService()
    return _default_financial_gate
