"""Business service for Zero Knowledge Memory Vault and Provenance Watermarking (Item 159).

[INPUT]
- SealMemoryRequest, UnsealMemoryRequest, ExportDistilledRequest, VerifyWatermarkRequest.

[OUTPUT]
- EncryptedEnvelopeDTO, DistilledMemoryItemDTO, DistilledExportPackageDTO, ProvenanceWatermarkDTO.

[POS]
- Service layer in myrm-agent-server/app/services/memory/zk_vault_watermark_service.py.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.zk_vault_watermark import (
    DistilledExportPackage,
    DistilledMemoryItem,
    EncryptedEnvelope,
    ProvenanceWatermark,
    ZeroKnowledgeMemoryVaultManager,
)

from app.schemas.zk_vault_watermark import (
    DistilledExportPackageDTO,
    DistilledMemoryItemDTO,
    EncryptedEnvelopeDTO,
    ExportDistilledRequest,
    MemorySensitivityTierDTO,
    ProvenanceWatermarkDTO,
    ResidencyCheckResponse,
    SealMemoryRequest,
    UnlockResidencyRequest,
    UnsealMemoryRequest,
    VerifyResidencyRequest,
    VerifyWatermarkRequest,
)


class ZkVaultWatermarkService:
    """Orchestrates envelope encryption, distilled export packaging, and invisible watermarks."""

    def __init__(
        self,
        manager: ZeroKnowledgeMemoryVaultManager | None = None,
    ) -> None:
        self.manager = manager or ZeroKnowledgeMemoryVaultManager()

    @staticmethod
    def _envelope_to_dto(env: EncryptedEnvelope) -> EncryptedEnvelopeDTO:
        return EncryptedEnvelopeDTO(
            ciphertext_hex=env.ciphertext_hex,
            iv_hex=env.iv_hex,
            salt_hex=env.salt_hex,
            encrypted_dek_hex=env.encrypted_dek_hex,
            algorithm=env.algorithm,
            created_at=env.created_at,
        )

    @staticmethod
    def _item_to_dto(item: DistilledMemoryItem) -> DistilledMemoryItemDTO:
        return DistilledMemoryItemDTO(
            memory_id=item.memory_id,
            content=item.content,
            sensitivity_tier=item.sensitivity_tier,
            category=item.category,
            redacted=item.redacted,
        )

    @staticmethod
    def _watermark_to_dto(wm: ProvenanceWatermark) -> ProvenanceWatermarkDTO:
        return ProvenanceWatermarkDTO(
            tenant_id=wm.tenant_id,
            user_id=wm.user_id,
            timestamp_iso=wm.timestamp_iso,
            signature=wm.signature,
        )

    def seal_memory(self, req: SealMemoryRequest) -> EncryptedEnvelopeDTO:
        """Encrypt memory payload with transient DEK sealed by user passphrase."""
        envelope = self.manager.seal_and_store_memory(
            memory_id=req.memory_id,
            content=req.content,
            sensitivity_tier=req.sensitivity_tier,
            category=req.category,
            passphrase=req.passphrase,
        )
        return self._envelope_to_dto(envelope)

    def unseal_memory(self, req: UnsealMemoryRequest) -> DistilledMemoryItemDTO:
        """Unseal encrypted envelope with passphrase and return memory record."""
        item = self.manager.unseal_memory(
            memory_id=req.memory_id,
            passphrase=req.passphrase,
        )
        return self._item_to_dto(item)

    def list_memories(
        self,
        tier: MemorySensitivityTierDTO | None = None,
    ) -> list[DistilledMemoryItemDTO]:
        """List unsealed memory records optionally filtered by sensitivity tier."""
        items = self.manager.list_memories(tier=tier)
        return [self._item_to_dto(it) for it in items]

    def export_distilled(
        self, req: ExportDistilledRequest
    ) -> DistilledExportPackageDTO:
        """Export sanitized memories with invisible zero-width provenance watermark."""
        pkg: DistilledExportPackage = self.manager.export_distilled_package(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            target_tier=req.target_tier,
            redact_pii=req.redact_pii,
            timestamp_iso=req.timestamp_iso,
        )
        return DistilledExportPackageDTO(
            tenant_id=pkg.tenant_id,
            target_tier=pkg.target_tier,
            exported_at=pkg.exported_at,
            items=[self._item_to_dto(it) for it in pkg.items],
            watermarked_text=pkg.watermarked_text,
            watermark_signature=pkg.watermark_signature,
        )

    def verify_watermark(
        self, req: VerifyWatermarkRequest
    ) -> ProvenanceWatermarkDTO | None:
        """Extract and verify invisible provenance watermark from text."""
        wm = self.manager.verify_exported_watermark(req.exported_text)
        if wm is None:
            return None
        return self._watermark_to_dto(wm)

    def verify_residency(
        self, req: VerifyResidencyRequest
    ) -> ResidencyCheckResponse:
        """Verify that current runtime matches bound sandbox fingerprint."""
        ok, diag = self.manager.verify_sandbox_residency(
            instance_guid=req.instance_guid,
            volume_id=req.volume_id,
            tenant_id=req.tenant_id,
        )
        return ResidencyCheckResponse(allowed=ok, diagnostic=diag)

    def unlock_residency(self, req: UnlockResidencyRequest) -> bool:
        """Unlock hardware binding and rebind to new sandbox instance."""
        return self.manager.unlock_sandbox_residency(
            provided_passphrase=req.provided_passphrase,
            expected_passphrase=req.expected_passphrase,
            new_instance_guid=req.new_instance_guid,
            new_volume_id=req.new_volume_id,
            tenant_id=req.tenant_id,
        )
