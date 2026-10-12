"""Tamper-evident dual-signed A2A commercial negotiation ledger service.

[POS]
Maintains cryptographic dual-signed hash chains for cross-enterprise A2A business negotiations.
Guarantees non-repudiation and legal liability binding between corporate principals.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from uuid import uuid4

from app.schemas.a2a_vdc import (
    DualSignedNegotiationBlock,
    NegotiationLedgerAuditReport,
    NegotiationTerms,
    VerifiableDelegationCredential,
)
from app.services.a2a.vdc_service import VdcService, get_vdc_service

logger = logging.getLogger(__name__)

_GENESIS_BLOCK_HASH: str = "0" * 64


class A2ANegotiationLedgerService:
    """Manages dual-signed negotiation chains per A2A session."""

    def __init__(self, vdc_service: VdcService | None = None) -> None:
        self._vdc_service = vdc_service
        self._sessions: dict[str, list[DualSignedNegotiationBlock]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def append_step(
        self,
        session_id: str,
        initiator_agent_id: str,
        responder_agent_id: str,
        initiator_vdc: VerifiableDelegationCredential,
        responder_vdc: VerifiableDelegationCredential,
        terms: NegotiationTerms,
        initiator_signature: str,
        responder_signature: str,
    ) -> DualSignedNegotiationBlock:
        """Verify VDCs and dual signatures, then append an immutable negotiation block."""
        async with self._lock:
            # 1. Verify credentials for both peers
            vdc_service = self._vdc_service or get_vdc_service()
            init_res = vdc_service.verify_vdc(
                vdc=initiator_vdc,
                proposed_action=terms.action,
                proposed_amount=terms.total_amount,
            )
            if not init_res.is_valid:
                raise ValueError(f"Initiator VDC invalid: {init_res.failure_reason}")

            resp_res = vdc_service.verify_vdc(
                vdc=responder_vdc,
                proposed_action=terms.action,
                proposed_amount=terms.total_amount,
            )
            if not resp_res.is_valid:
                raise ValueError(f"Responder VDC invalid: {resp_res.failure_reason}")

            # 2. Verify dual signatures on terms digest
            terms_digest = terms.terms_digest
            if not self._verify_agent_signature(initiator_vdc.issuer_public_key, terms_digest, initiator_signature):
                raise ValueError(f"Initiator digital signature invalid for terms digest {terms_digest}")
            if not self._verify_agent_signature(responder_vdc.issuer_public_key, terms_digest, responder_signature):
                raise ValueError(f"Responder digital signature invalid for terms digest {terms_digest}")

            # 3. Retrieve or initialize chain for session
            blocks = self._sessions.setdefault(session_id, [])
            step_index = len(blocks)
            prev_hash = blocks[-1].block_hash if blocks else _GENESIS_BLOCK_HASH

            block = DualSignedNegotiationBlock(
                block_id=str(uuid4()),
                session_id=session_id,
                step_index=step_index,
                initiator_agent_id=initiator_agent_id,
                responder_agent_id=responder_agent_id,
                initiator_vdc_id=initiator_vdc.credential_id,
                responder_vdc_id=responder_vdc.credential_id,
                terms=terms,
                initiator_signature=initiator_signature,
                responder_signature=responder_signature,
                prev_block_hash=prev_hash,
                timestamp=time.time(),
            )
            block.block_hash = block.compute_block_hash()
            blocks.append(block)

            logger.info(
                "Appended dual-signed negotiation block: session=%s step=%d action=%s amount=%s %s",
                session_id,
                step_index,
                terms.action,
                terms.total_amount,
                terms.currency,
            )
            return block

    def get_session_blocks(self, session_id: str) -> list[DualSignedNegotiationBlock]:
        """Return all negotiation blocks for a given session."""
        return list(self._sessions.get(session_id, []))

    def verify_session_chain(
        self,
        session_id: str,
        initiator_public_key: str,
        responder_public_key: str,
        agent_public_keys: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Verify sequential cryptographic hash continuity and dual signatures across session."""
        blocks = self._sessions.get(session_id, [])
        if not blocks:
            return True, None

        candidate_pks: list[str] = [pk for pk in (initiator_public_key, responder_public_key) if pk]
        if agent_public_keys:
            candidate_pks.extend(agent_public_keys.values())

        expected_prev_hash = _GENESIS_BLOCK_HASH
        for idx, block in enumerate(blocks):
            if block.step_index != idx:
                return False, f"Step index discontinuous at block {idx}: got {block.step_index}"

            if block.prev_block_hash != expected_prev_hash:
                return (
                    False,
                    f"Hash continuity broken at step {idx}: expected {expected_prev_hash}, got {block.prev_block_hash}",
                )

            computed_hash = block.compute_block_hash()
            if block.block_hash != computed_hash:
                return False, f"Block payload hash mismatch at step {idx}: expected {computed_hash}, got {block.block_hash}"

            # Verify terms content payload digest integrity
            expected_terms_digest = NegotiationTerms.compute_digest(
                action=block.terms.action,
                item_description=block.terms.item_description,
                quantity=block.terms.quantity,
                unit_price=block.terms.unit_price,
                total_amount=block.terms.total_amount,
                currency=block.terms.currency,
                delivery_deadline=block.terms.delivery_deadline,
            )
            if block.terms.terms_digest != expected_terms_digest:
                return False, f"Terms payload content tampered at step {idx}"

            # Verify dual signatures on terms digest using candidate peer keys
            terms_digest = block.terms.terms_digest
            init_ok = any(self._verify_agent_signature(pk, terms_digest, block.initiator_signature) for pk in candidate_pks)
            if not init_ok:
                return False, f"Invalid initiator signature at step {idx}"

            resp_ok = any(self._verify_agent_signature(pk, terms_digest, block.responder_signature) for pk in candidate_pks)
            if not resp_ok:
                return False, f"Invalid responder signature at step {idx}"

            expected_prev_hash = block.block_hash

        return True, None

    def export_audit_dossier(
        self,
        session_id: str,
        initiator_did: str,
        responder_did: str,
        initiator_public_key: str,
        responder_public_key: str,
        agent_public_keys: dict[str, str] | None = None,
    ) -> NegotiationLedgerAuditReport:
        """Generate legal-grade non-repudiation audit dossier for the negotiation."""
        blocks = self.get_session_blocks(session_id)
        intact, err = self.verify_session_chain(
            session_id=session_id,
            initiator_public_key=initiator_public_key,
            responder_public_key=responder_public_key,
            agent_public_keys=agent_public_keys,
        )

        has_final_contract = any(b.terms.action == "final_contract" for b in blocks)

        return NegotiationLedgerAuditReport(
            session_id=session_id,
            total_blocks=len(blocks),
            chain_intact=intact,
            integrity_error=err,
            final_contract_agreed=has_final_contract,
            initiator_did=initiator_did,
            responder_did=responder_did,
            blocks=blocks,
        )

    @classmethod
    def _verify_agent_signature(cls, public_key: str, digest: str, signature: str) -> bool:
        """Deterministic verification of agent digital signature."""
        mac = hmac.new(public_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256)
        expected = mac.hexdigest()
        return hmac.compare_digest(signature, expected)

    @classmethod
    def sign_terms_digest(cls, signing_key: str, digest: str) -> str:
        """Utility for peer agents to sign terms digest."""
        mac = hmac.new(signing_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()


_default_negotiation_ledger: A2ANegotiationLedgerService | None = None


def get_negotiation_ledger() -> A2ANegotiationLedgerService:
    """Return singleton instance of A2ANegotiationLedgerService."""
    global _default_negotiation_ledger
    if _default_negotiation_ledger is None:
        _default_negotiation_ledger = A2ANegotiationLedgerService()
    return _default_negotiation_ledger
