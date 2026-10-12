"""Service layer for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- TrustDirectoryRequest, ResolveProjectRemoteRequest.

[OUTPUT]
- TrustDirectoryResponse, CheckDirectoryTrustResponse, ResolveProjectRemoteResponse.

[POS]
- Server service wrapping harness directory trust store and single-point resolver.
"""

from __future__ import annotations

import logging
import os

from myrm_agent_harness.core.security.directory_trust_remote_memory import (
    DirectoryTrustStore,
    ProjectMemoryConfig,
    SinglePointRemoteMemoryResolver,
)

from app.schemas.directory_trust_remote_memory import (
    CheckDirectoryTrustResponse,
    ResolveProjectRemoteRequest,
    ResolveProjectRemoteResponse,
    TrustDirectoryRequest,
    TrustDirectoryResponse,
)

logger = logging.getLogger(__name__)


class DirectoryTrustRemoteMemoryService:
    """Coordinates directory trust state and single-point resolution for project memory."""

    def __init__(self, initial_trusted_dirs: list[str] | None = None) -> None:
        self._trust_store = DirectoryTrustStore(
            initial_trusted_dirs=initial_trusted_dirs
        )
        self._resolver = SinglePointRemoteMemoryResolver()

    def set_directory_trust(
        self, request: TrustDirectoryRequest
    ) -> TrustDirectoryResponse:
        """Add or remove a directory from the trusted registry."""
        if request.action == "trust":
            canonical = self._trust_store.trust_directory(request.directory)
            is_trusted = True
        else:
            self._trust_store.untrust_directory(request.directory)
            canonical = os.path.realpath(
                os.path.abspath(os.path.expanduser(request.directory))
            )
            is_trusted = False

        return TrustDirectoryResponse(
            directory=request.directory,
            canonical_path=canonical,
            is_trusted=is_trusted,
            action=request.action,
        )

    def check_directory_trust(
        self, directory: str
    ) -> CheckDirectoryTrustResponse:
        """Check whether a specific directory is trusted."""
        canonical = os.path.realpath(
            os.path.abspath(os.path.expanduser(directory))
        )
        is_trusted = self._trust_store.is_directory_trusted(directory)
        return CheckDirectoryTrustResponse(
            directory=directory,
            canonical_path=canonical,
            is_trusted=is_trusted,
        )

    def list_trusted_directories(self) -> list[str]:
        """Return list of all trusted directory roots."""
        return self._trust_store.list_trusted_directories()

    def resolve_project_remote(
        self, request: ResolveProjectRemoteRequest
    ) -> ResolveProjectRemoteResponse:
        """Atomically resolve project memory settings against directory trust gates."""
        cfg = ProjectMemoryConfig(
            local_scope=request.config.local_scope,
            domain=request.config.domain,
            remote_url=request.config.remote_url,
            remote_token=request.config.remote_token,
            remote_scopes=request.config.remote_scopes,
        )

        resolved = self._resolver.resolve_from_config(
            config=cfg,
            config_path=request.config_path,
            trust_store=self._trust_store,
        )

        remote_url = (
            resolved.remote_memory.url if resolved.remote_memory else None
        )
        remote_token = (
            resolved.remote_memory.token if resolved.remote_memory else None
        )
        remote_scopes = (
            resolved.remote_memory.scopes if resolved.remote_memory else []
        )

        return ResolveProjectRemoteResponse(
            config_path=resolved.config_path,
            config_dir=resolved.config_dir,
            trust_status=resolved.trust_status.value,
            is_trusted=resolved.is_trusted,
            remote_url=remote_url,
            remote_token=remote_token,
            remote_scopes=remote_scopes,
            refused_from=resolved.refused_from,
            refusal_notice=resolved.refusal_notice,
            effective_scope=resolved.effective_scope,
            is_outbound_authorized=resolved.is_outbound_authorized,
        )


_GLOBAL_TRUST_SERVICE: DirectoryTrustRemoteMemoryService | None = None


def get_directory_trust_remote_memory_service() -> (
    DirectoryTrustRemoteMemoryService
):
    """FastAPI dependency provider for DirectoryTrustRemoteMemoryService."""
    global _GLOBAL_TRUST_SERVICE
    if _GLOBAL_TRUST_SERVICE is None:
        _GLOBAL_TRUST_SERVICE = DirectoryTrustRemoteMemoryService()
    return _GLOBAL_TRUST_SERVICE
