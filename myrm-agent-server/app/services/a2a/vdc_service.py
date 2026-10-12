"""Service for Verifiable AI Delegation Credentials (VDC) issuance and offline attestation.

[POS]
Issues enterprise-backed delegation credentials limiting agent authority (amounts, time, actions).
Provides sub-millisecond offline verification of peer credentials to ensure legitimate authority
and eliminate AI hallucination liability disputes.
"""

from __future__ import annotations

import logging
import os
import time
from uuid import uuid4

from app.schemas.a2a_vdc import (
    VdcVerificationResult,
    VerifiableDelegationCredential,
)

logger = logging.getLogger(__name__)

_DEFAULT_ENTERPRISE_KEY: str = os.getenv(
    "MYRM_ENTERPRISE_SIGNING_KEY",
    "acme_corp_internal_delegation_secret_key_2026",
)


class VdcService:
    """Manages creation, storage, and cryptographic validation of VDCs."""

    def __init__(self, enterprise_key: str = _DEFAULT_ENTERPRISE_KEY) -> None:
        self._enterprise_key = enterprise_key
        self._credentials: dict[str, VerifiableDelegationCredential] = {}

    def issue_vdc(
        self,
        issuer_did: str,
        issuer_name: str,
        holder_agent_id: str,
        holder_name: str,
        max_transaction_amount: float,
        allowed_actions: list[str],
        validity_duration_seconds: float = 86400 * 30,  # default 30 days
        currency: str = "USD",
        issuer_public_key: str = "pk_ed25519_acme_master_key_fingerprint",
    ) -> VerifiableDelegationCredential:
        """Issue a digitally signed delegation credential bound to an agent."""
        now = time.time()
        cred_id = str(uuid4())

        vdc = VerifiableDelegationCredential(
            credential_id=cred_id,
            issuer_did=issuer_did,
            issuer_name=issuer_name,
            holder_agent_id=holder_agent_id,
            holder_name=holder_name,
            max_transaction_amount=max_transaction_amount,
            currency=currency,
            valid_from=now,
            valid_until=now + validity_duration_seconds,
            allowed_actions=allowed_actions,
            issuer_public_key=issuer_public_key,
        )
        vdc.signature = vdc.sign(self._enterprise_key)
        self._credentials[cred_id] = vdc

        logger.info(
            "Issued VDC %s: issuer=%s holder=%s max_amount=%s %s",
            cred_id,
            issuer_did,
            holder_agent_id,
            max_transaction_amount,
            currency,
        )
        return vdc

    def get_vdc(self, credential_id: str) -> VerifiableDelegationCredential | None:
        """Retrieve credential from local storage by ID."""
        return self._credentials.get(credential_id)

    def verify_vdc(
        self,
        vdc: VerifiableDelegationCredential,
        proposed_action: str | None = None,
        proposed_amount: float | None = None,
        verification_time: float | None = None,
    ) -> VdcVerificationResult:
        """Verify peer agent credential authenticity, expiration, and operational scope."""
        now = verification_time if verification_time is not None else time.time()

        # 1. Cryptographic signature check
        if not vdc.verify(self._enterprise_key):
            logger.error("VDC signature verification failed for credential %s", vdc.credential_id)
            return VdcVerificationResult(
                is_valid=False,
                failure_reason="Invalid cryptographic signature or tampered payload",
                credential_id=vdc.credential_id,
                issuer_did=vdc.issuer_did,
                holder_agent_id=vdc.holder_agent_id,
                amount_permitted=False,
                action_permitted=False,
                is_expired=False,
            )

        # 2. Time validity check
        is_expired = now < vdc.valid_from or now > vdc.valid_until
        if is_expired:
            return VdcVerificationResult(
                is_valid=False,
                failure_reason=f"Credential expired or not yet valid (now={now}, valid={vdc.valid_from}..{vdc.valid_until})",
                credential_id=vdc.credential_id,
                issuer_did=vdc.issuer_did,
                holder_agent_id=vdc.holder_agent_id,
                amount_permitted=False,
                action_permitted=False,
                is_expired=True,
            )

        # 3. Action whitelist check
        action_permitted = True
        if proposed_action and proposed_action not in vdc.allowed_actions:
            action_permitted = False
            return VdcVerificationResult(
                is_valid=False,
                failure_reason=f"Proposed action '{proposed_action}' not authorized in VDC: {vdc.allowed_actions}",
                credential_id=vdc.credential_id,
                issuer_did=vdc.issuer_did,
                holder_agent_id=vdc.holder_agent_id,
                amount_permitted=False,
                action_permitted=False,
                is_expired=False,
            )

        # 4. Amount ceiling check
        amount_permitted = True
        if proposed_amount is not None and proposed_amount > vdc.max_transaction_amount:
            amount_permitted = False
            return VdcVerificationResult(
                is_valid=False,
                failure_reason=(
                    f"Proposed amount {proposed_amount} exceeds maximum authorized ceiling "
                    f"{vdc.max_transaction_amount} {vdc.currency}"
                ),
                credential_id=vdc.credential_id,
                issuer_did=vdc.issuer_did,
                holder_agent_id=vdc.holder_agent_id,
                amount_permitted=False,
                action_permitted=action_permitted,
                is_expired=False,
            )

        return VdcVerificationResult(
            is_valid=True,
            failure_reason=None,
            credential_id=vdc.credential_id,
            issuer_did=vdc.issuer_did,
            holder_agent_id=vdc.holder_agent_id,
            amount_permitted=amount_permitted,
            action_permitted=action_permitted,
            is_expired=False,
        )


_default_vdc_service: VdcService | None = None


def get_vdc_service() -> VdcService:
    """Return singleton instance of VdcService."""
    global _default_vdc_service
    if _default_vdc_service is None:
        _default_vdc_service = VdcService()
    return _default_vdc_service
