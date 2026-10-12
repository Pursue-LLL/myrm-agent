"""Service layer for Directory Trust Gate.

[INPUT]
- myrm_agent_harness.core.security.dir_trust_gate::DirTrustGate (POS: Security gate enforcing directory trust boundaries)
- app.schemas.dir_trust_gate::DirectoryTrustEvaluateRequest (POS: Schema for evaluation requests)

[OUTPUT]
- DirTrustGateService: Manages directory authorization lifecycle and evaluation queries.

[POS]
Service layer bridging Directory Trust Gate evaluation and trust storage to FastAPI routers.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.dir_trust_gate import (
    DirectoryTrustStore,
    DirTrustGate,
    ProjectRemoteConfig,
)

from app.schemas.dir_trust_gate import (
    DirectoryTrustActionResponse,
    DirectoryTrustEvaluateRequest,
    DirectoryTrustEvaluateResponse,
    DirectoryTrustListResponse,
)


class DirTrustGateService:
    """Service wrapping Directory Trust Gate evaluation and trust management."""

    def __init__(self, trust_store: DirectoryTrustStore | None = None) -> None:
        self._trust_store = trust_store or DirectoryTrustStore()
        self._gate = DirTrustGate(trust_store=self._trust_store)

    def evaluate_directory(
        self, request: DirectoryTrustEvaluateRequest
    ) -> DirectoryTrustEvaluateResponse:
        """Evaluate repository configuration against directory trust boundaries."""
        config = ProjectRemoteConfig(
            remote_url=request.remote_url,
            remote_token=request.remote_token,
            scope=request.scope,
        )
        gated = self._gate.evaluate(request.directory, config)
        return DirectoryTrustEvaluateResponse(
            sanitized_directory=gated.sanitized_directory,
            is_trusted=gated.is_trusted,
            is_remote_allowed=gated.is_remote_allowed,
            allowed_remote_url=gated.allowed_remote_url,
            allowed_remote_token=gated.allowed_remote_token,
            effective_scope=gated.effective_scope,
            warning_message=gated.warning_message,
        )

    def trust_directory(
        self, directory: str, reason: str = "manual_grant"
    ) -> DirectoryTrustActionResponse:
        """Explicitly authorize a directory."""
        canonical = self._trust_store.trust(directory, reason=reason)
        return DirectoryTrustActionResponse(
            directory=canonical,
            success=True,
            action="trust",
            is_trusted=True,
        )

    def untrust_directory(self, directory: str) -> DirectoryTrustActionResponse:
        """Revoke trust from a directory."""
        canonical = DirectoryTrustStore.normalize_directory(directory)
        was_trusted = self._trust_store.untrust(directory)
        return DirectoryTrustActionResponse(
            directory=canonical,
            success=was_trusted,
            action="untrust",
            is_trusted=False,
        )

    def list_trusted_directories(self) -> DirectoryTrustListResponse:
        """List all canonical trusted directories."""
        dirs = self._trust_store.list_trusted()
        return DirectoryTrustListResponse(
            trusted_directories=dirs,
            count=len(dirs),
        )


_instance: DirTrustGateService | None = None


def get_dir_trust_gate_service() -> DirTrustGateService:
    """Get singleton instance of DirTrustGateService."""
    global _instance
    if _instance is None:
        _instance = DirTrustGateService()
    return _instance
