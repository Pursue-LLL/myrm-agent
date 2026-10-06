"""Service layer for Local-First Zero-Leak Vault and Zero-Knowledge E2EE Sharing Gateway.

[INPUT]
Standard library base64, hashlib, secrets, time, datetime, pydantic schemas.

[OUTPUT]
LocalFirstVaultService, get_local_first_vault_service.

[POS]
Service implementation managing in-situ DLP sanitization, client-side encrypted vault items,
and zero-knowledge ephemeral sharing links.
"""

from __future__ import annotations

import base64
import logging

from myrm_agent_harness.core.security.local_first_vault import (
    DlpRedactionResult,
    E2eeShareEnvelope,
    LocalVaultItem,
    VaultStorageMode,
    ZeroKnowledgeE2eeGateway,
)

from app.schemas.local_first_vault import (
    CreateE2eeShareRequest,
    DecryptE2eeShareRequest,
    DecryptE2eeShareResponse,
    DlpRedactionMatchResponse,
    DlpSanitizeRequest,
    DlpSanitizeResponse,
    E2eeShareResponse,
    LocalArtifactResponse,
    RegisterLocalArtifactRequest,
)

logger = logging.getLogger(__name__)


class LocalFirstVaultService:
    """Coordinates local-first physical artifact storage, in-situ DLP sanitization, and E2EE sharing."""

    def __init__(
        self, gateway: ZeroKnowledgeE2eeGateway | None = None
    ) -> None:
        self.gateway = gateway or ZeroKnowledgeE2eeGateway()

    def sanitize_content(self, req: DlpSanitizeRequest) -> DlpSanitizeResponse:
        """Run transparent in-situ DLP redaction across text content."""
        result = self.gateway.dlp.sanitize_content(
            content=req.content,
            enable_price_redaction=req.enable_price_redaction,
        )
        return self._convert_dlp(result)

    def register_local_artifact(
        self, req: RegisterLocalArtifactRequest
    ) -> LocalArtifactResponse:
        """Store artifact metadata under the local-first physical disk invariant."""
        mode = VaultStorageMode(req.storage_mode.lower())
        item = self.gateway.register_local_artifact(
            artifact_id=req.artifact_id,
            title=req.title,
            local_path=req.local_path,
            content=req.content,
            storage_mode=mode,
        )
        logger.info(
            "Registered local-first artifact '%s' at '%s' (mode=%s, cloud_synced=False)",
            item.artifact_id,
            item.local_path,
            item.storage_mode,
        )
        return self._convert_item(item)

    def get_local_artifact(self, artifact_id: str) -> LocalArtifactResponse | None:
        """Retrieve local artifact record by artifact_id."""
        item = self.gateway.get_local_artifact(artifact_id)
        if item is None:
            return None
        return self._convert_item(item)

    def list_local_artifacts(self) -> list[LocalArtifactResponse]:
        """List all artifacts preserved under local-first storage."""
        return [self._convert_item(i) for i in self.gateway.list_local_artifacts()]

    def create_e2ee_share(
        self, req: CreateE2eeShareRequest
    ) -> E2eeShareResponse:
        """Generate zero-knowledge AES-256-GCM encrypted envelope with in-situ DLP."""
        envelope, key = self.gateway.create_e2ee_share(
            artifact_id=req.artifact_id,
            plaintext_content=req.plaintext_content,
            ttl_seconds=req.ttl_seconds,
            enable_dlp_sanitization=req.enable_dlp_sanitization,
        )
        key_b64 = base64.b64encode(key).decode("utf-8")
        url_fragment = f"#share_id={envelope.share_id}&key={key_b64}"
        logger.info(
            "Created zero-knowledge E2EE share envelope '%s' for artifact '%s'",
            envelope.share_id,
            envelope.artifact_id,
        )
        return self._convert_envelope(envelope, key_b64, url_fragment)

    def decrypt_e2ee_share(
        self, share_id: str, req: DecryptE2eeShareRequest
    ) -> DecryptE2eeShareResponse:
        """Decrypt E2EE envelope using client-held symmetric key."""
        try:
            key_bytes = base64.b64decode(req.client_key_b64)
        except Exception as exc:
            raise ValueError(f"Invalid base64 client key: {exc}") from exc

        decrypted_text = self.gateway.decrypt_envelope(share_id, key_bytes)
        envelope = self.gateway.get_envelope(share_id)
        dlp_passed = envelope.dlp_audit_passed if envelope else True

        return DecryptE2eeShareResponse(
            share_id=share_id,
            decrypted_content=decrypted_text,
            dlp_audit_passed=dlp_passed,
        )

    @staticmethod
    def _convert_dlp(res: DlpRedactionResult) -> DlpSanitizeResponse:
        matches = [
            DlpRedactionMatchResponse(
                category=m.category.value,
                original_snippet=m.original_snippet,
                redacted_snippet=m.redacted_snippet,
                start=m.start,
                end=m.end,
            )
            for m in res.matches
        ]
        return DlpSanitizeResponse(
            original_length=res.original_length,
            redacted_length=res.redacted_length,
            total_redactions=res.total_redactions,
            categories_found=[c.value for c in res.categories_found],
            matches=matches,
            sanitized_content=res.sanitized_content,
        )

    @staticmethod
    def _convert_item(item: LocalVaultItem) -> LocalArtifactResponse:
        return LocalArtifactResponse(
            artifact_id=item.artifact_id,
            title=item.title,
            local_path=item.local_path,
            storage_mode=item.storage_mode.value,
            is_cloud_synced=item.is_cloud_synced,
            content_hash=item.content_hash,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _convert_envelope(
        env: E2eeShareEnvelope,
        key_b64: str,
        url_fragment: str,
    ) -> E2eeShareResponse:
        return E2eeShareResponse(
            share_id=env.share_id,
            artifact_id=env.artifact_id,
            ciphertext_b64=env.ciphertext_b64,
            nonce_b64=env.nonce_b64,
            salt_b64=env.salt_b64,
            key_hash=env.key_hash,
            dlp_audit_passed=env.dlp_audit_passed,
            client_key_b64=key_b64,
            share_url_fragment=url_fragment,
            expires_at=env.expires_at,
            created_at=env.created_at,
        )


_service_instance: LocalFirstVaultService | None = None


def get_local_first_vault_service() -> LocalFirstVaultService:
    """FastAPI dependency provider for LocalFirstVaultService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LocalFirstVaultService()
    return _service_instance


def reset_local_first_vault_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None
