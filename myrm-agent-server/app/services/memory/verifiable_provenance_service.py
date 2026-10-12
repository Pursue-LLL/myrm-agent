"""
[INPUT]: ResidencyProofRequest, PhysicalPurgeRequest, InspectPiiRequest, TokenGenerateRequest
[OUTPUT]: ResidencyProofResponse, DestructionReceiptResponse, PiiShieldResponse, TokenGenerateResponse
[POS]: myrm-agent-server/app/services/memory/verifiable_provenance_service.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from myrm_agent_harness.toolkits.memory.verifiable_provenance import (
    FailClosedSecurityException,
    TenantSandboxContext,
    VerifiableProvenanceManager,
)

from app.schemas.verifiable_provenance import (
    DestructionReceiptResponse,
    InspectPiiRequest,
    PhysicalPurgeRequest,
    PiiShieldResponse,
    ResidencyProofRequest,
    ResidencyProofResponse,
    TenantSandboxContextDTO,
    TokenGenerateRequest,
    TokenGenerateResponse,
)


class VerifiableProvenanceService:
    """Business service orchestrating verifiable memory residency, purge, and PII protection."""

    def __init__(
        self,
        volume_root_boundary: Optional[Path] = None,
        master_secret: Optional[str] = None,
    ) -> None:
        root_dir = volume_root_boundary or Path(
            os.environ.get("MYRM_SANDBOX_VOLUME_ROOT", "/tmp/myrm_sandbox_volumes")
        ).resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        secret = master_secret or os.environ.get(
            "MYRM_PROVENANCE_MASTER_SECRET", "default-sandbox-cluster-provenance-key-2026"
        )
        self._manager = VerifiableProvenanceManager(
            volume_root_boundary=root_dir,
            master_environment_secret=secret,
            overwrite_passes=3,
        )

    @property
    def manager(self) -> VerifiableProvenanceManager:
        return self._manager

    def generate_token(self, req: TokenGenerateRequest) -> TokenGenerateResponse:
        """Issue cryptographically signed environment token for tenant volume binding."""
        token = self._manager.guard.generate_token(req.tenant_id, req.sandbox_id, req.volume_id)
        return TokenGenerateResponse(
            environment_token=token,
            tenant_id=req.tenant_id,
            sandbox_id=req.sandbox_id,
            volume_id=req.volume_id,
        )

    def prove_residency(self, req: ResidencyProofRequest) -> ResidencyProofResponse:
        """Compute transparent physical residency proof ensuring zero-shared storage."""
        ctx = self._to_harness_context(req.context)
        file_path = Path(req.file_path)
        proof = self._manager.verify_and_prove_residency(file_path, ctx, req.extra_metadata)
        return ResidencyProofResponse(
            tenant_id=proof.tenant_id,
            sandbox_id=proof.sandbox_id,
            volume_id=proof.volume_id,
            storage_path=proof.storage_path,
            volume_mount_point=proof.volume_mount_point,
            file_inode=proof.file_inode,
            content_sha256=proof.content_sha256,
            is_exclusive_volume=proof.is_exclusive_volume,
            verified_at=proof.verified_at,
            metadata=proof.metadata,
        )

    def purge_storage(self, req: PhysicalPurgeRequest) -> DestructionReceiptResponse:
        """Execute verifiable multi-pass physical purge and issue destruction receipt."""
        ctx = self._to_harness_context(req.context)
        file_path = Path(req.file_path)
        receipt = self._manager.verify_and_purge_storage(file_path, ctx)
        return DestructionReceiptResponse(
            receipt_id=receipt.receipt_id,
            tenant_id=receipt.tenant_id,
            sandbox_id=receipt.sandbox_id,
            volume_id=receipt.volume_id,
            purged_storage_path=receipt.purged_storage_path,
            bytes_overwritten=receipt.bytes_overwritten,
            overwrite_passes=receipt.overwrite_passes,
            status=receipt.status.value,
            destruction_digest=receipt.destruction_digest,
            completed_at=receipt.completed_at,
        )

    def inspect_pii(self, req: InspectPiiRequest) -> PiiShieldResponse:
        """Inspect and sanitize text prior to persistence to prevent PII leakage."""
        detection = self._manager.inspect_memory_content(req.text)
        return PiiShieldResponse(
            intercepted=detection.intercepted,
            detected_categories=[c.value for c in detection.detected_categories],
            sanitized_text=detection.sanitized_text,
            masked_spans=detection.masked_spans,
            has_child_privacy_violation=detection.has_child_privacy_violation,
        )

    def _to_harness_context(self, dto: TenantSandboxContextDTO) -> TenantSandboxContext:
        return TenantSandboxContext(
            tenant_id=dto.tenant_id,
            sandbox_id=dto.sandbox_id,
            volume_id=dto.volume_id,
            environment_token=dto.environment_token,
        )
