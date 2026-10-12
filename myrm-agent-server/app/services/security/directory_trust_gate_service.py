"""Service layer for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- TrustDirectoryRequest, UntrustDirectoryRequest, ResolveDirectoryTrustRequest.

[OUTPUT]
- TrustDirectoryResponse, UntrustDirectoryResponse, ListTrustedDirectoriesResponse, ResolvedDirectoryTrustDto.

[POS]
- Server service wrapping harness directory trust store and single-point memory resolver.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.core.security.directory_trust_gate import (
    DirectoryTrustStore,
    ProjectMemoryConfig,
    RemoteMemoryTrustGate,
)

from app.schemas.directory_trust_gate import (
    ListTrustedDirectoriesResponse,
    ResolvedDirectoryTrustDto,
    ResolveDirectoryTrustRequest,
    TrustDirectoryRequest,
    TrustDirectoryResponse,
    UntrustDirectoryRequest,
    UntrustDirectoryResponse,
)

logger = logging.getLogger(__name__)


class DirectoryTrustGateService:
    """Manages workspace directory trust boundaries and gates remote memory configuration."""

    def __init__(self, trust_store: DirectoryTrustStore | None = None) -> None:
        self._trust_store = trust_store if trust_store is not None else DirectoryTrustStore()

    def trust_directory(self, request: TrustDirectoryRequest) -> TrustDirectoryResponse:
        """Mark a directory as trusted for configuration and remote memory access."""
        canonical = self._trust_store.trust_directory(request.directory)
        return TrustDirectoryResponse(
            directory=request.directory,
            canonical_path=canonical,
            trusted=True,
        )

    def untrust_directory(
        self, request: UntrustDirectoryRequest
    ) -> UntrustDirectoryResponse:
        """Revoke trust from a directory boundary."""
        removed = self._trust_store.untrust_directory(request.directory)
        return UntrustDirectoryResponse(
            directory=request.directory,
            removed=removed,
        )

    def list_trusted(self) -> ListTrustedDirectoriesResponse:
        """List all currently trusted filesystem directories."""
        trusted_list = self._trust_store.list_trusted_directories()
        return ListTrustedDirectoriesResponse(
            trusted_directories=trusted_list,
            count=len(trusted_list),
        )

    def resolve_directory_trust(
        self, request: ResolveDirectoryTrustRequest
    ) -> ResolvedDirectoryTrustDto:
        """Resolve memory configuration and evaluate directory trust boundaries."""
        cfg_override: ProjectMemoryConfig | None = None
        if request.config_override is not None:
            cfg_override = ProjectMemoryConfig(
                scope=request.config_override.scope,
                domain=request.config_override.domain,
                remote_url=request.config_override.remote_url,
                remote_token=request.config_override.remote_token,
                remote_scopes=request.config_override.remote_scopes,
            )

        resolved = RemoteMemoryTrustGate.resolve_from_directory(
            trust_store=self._trust_store,
            start_dir=Path(request.start_directory),
            config=cfg_override,
        )

        return ResolvedDirectoryTrustDto(
            config_path=resolved.config_path,
            config_dir=resolved.config_dir,
            is_directory_trusted=resolved.is_directory_trusted,
            effective_scope=resolved.effective_scope,
            effective_domain=resolved.effective_domain,
            remote_url=resolved.remote_url,
            remote_token=resolved.remote_token,
            remote_scopes=resolved.remote_scopes,
            refusal_notice=resolved.refusal_notice,
            decision=resolved.decision.value,
        )


_GLOBAL_SERVICE: DirectoryTrustGateService | None = None


def get_directory_trust_gate_service() -> DirectoryTrustGateService:
    """FastAPI dependency injection provider for DirectoryTrustGateService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = DirectoryTrustGateService()
    return _GLOBAL_SERVICE
