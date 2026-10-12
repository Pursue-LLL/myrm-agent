"""Service layer for Scoped Folder Permission Dialog and Sandbox Dynamic Mount Suite.

[POS] app/services/security/scoped_folder_sandbox_mount_service.py
[INPUT] app.schemas.scoped_folder_sandbox_mount, myrm_agent_harness.core.security.scoped_folder_sandbox_mount
[OUTPUT] ScopedFolderSandboxMountService, get_scoped_folder_mount_service
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.core.security.scoped_folder_sandbox_mount import (
    DynamicSandboxMountManager,
    FolderAccessMode,
    MountLifecyclePolicy,
    ScopedFolderGrant,
    SensitivePathGuard,
)

from app.schemas.scoped_folder_sandbox_mount import (
    DynamicMountSpecDTO,
    RevokeGrantResponse,
    ScopedFolderGrantDTO,
    ScopedFolderGrantRequest,
    ValidatePathSecurityRequest,
    ValidatePathSecurityResponse,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class ScopedFolderSandboxMountService:
    """Coordinates security-scoped folder authorization, blacklist checks, and sandbox dynamic mount projections."""

    def __init__(self) -> None:
        self._path_guard = SensitivePathGuard()
        self._mount_manager = DynamicSandboxMountManager(path_guard=self._path_guard)

    def validate_path_security(
        self, request: ValidatePathSecurityRequest
    ) -> ValidatePathSecurityResponse:
        """Evaluate candidate host path against sensitive system and credential blacklists."""
        result = self._path_guard.validate_path(request.path)
        return ValidatePathSecurityResponse(
            is_blocked=result.is_blocked,
            resolved_path=result.resolved_path,
            matched_rule=result.matched_rule,
            reason=result.reason,
        )

    def grant_folder_access(
        self, request: ScopedFolderGrantRequest
    ) -> ScopedFolderGrantDTO:
        """Authorize folder access and project sandbox virtual mount point."""
        access_mode = FolderAccessMode(request.access_mode.upper())
        lifecycle = MountLifecyclePolicy(request.lifecycle.upper())

        grant = self._mount_manager.grant_folder_access(
            folder_path=request.folder_path,
            access_mode=access_mode,
            lifecycle=lifecycle,
            lease_seconds=request.lease_seconds,
            alias_slug=request.alias_slug,
        )

        logger.info(
            "Granted scoped folder projection: grant_id=%s host='%s' mount='%s'",
            grant.grant_id,
            grant.folder_path,
            grant.sandbox_mount_path,
        )
        return self._grant_to_dto(grant)

    def get_mount_spec(self, grant_id: str) -> DynamicMountSpecDTO | None:
        """Fetch container virtualization mount specification for an active grant."""
        spec = self._mount_manager.get_mount_spec(grant_id)
        if spec is None:
            return None

        return DynamicMountSpecDTO(
            source_host_path=spec.source_host_path,
            sandbox_target_path=spec.sandbox_target_path,
            read_only=spec.read_only,
            grant_id=spec.grant_id,
        )

    def revoke_grant(self, grant_id: str) -> RevokeGrantResponse:
        """Revoke active folder grant and tear down its sandbox mount point."""
        revoked = self._mount_manager.revoke_grant(grant_id)
        msg = "Grant successfully revoked and sandbox mount unmounted." if revoked else "Grant not found or already revoked."
        return RevokeGrantResponse(
            grant_id=grant_id,
            revoked=revoked,
            message=msg,
        )

    def list_active_grants(self) -> list[ScopedFolderGrantDTO]:
        """List all currently active and unexpired folder grants."""
        grants = self._mount_manager.list_active_grants()
        return [self._grant_to_dto(g) for g in grants]

    def list_all_grants(self) -> list[ScopedFolderGrantDTO]:
        """List all historical folder grants including revoked entries."""
        grants = self._mount_manager.list_all_grants()
        return [self._grant_to_dto(g) for g in grants]

    @staticmethod
    def _grant_to_dto(grant: ScopedFolderGrant) -> ScopedFolderGrantDTO:
        """Convert a Harness ScopedFolderGrant to a typed REST DTO."""
        return ScopedFolderGrantDTO(
            grant_id=grant.grant_id,
            folder_path=grant.folder_path,
            alias_slug=grant.alias_slug,
            access_mode=grant.access_mode.value,
            lifecycle=grant.lifecycle.value,
            sandbox_mount_path=grant.sandbox_mount_path,
            granted_at=grant.granted_at,
            expires_at=grant.expires_at,
            is_revoked=grant.is_revoked,
            revoked_at=grant.revoked_at,
        )


_service_instance: ScopedFolderSandboxMountService | None = None


def get_scoped_folder_mount_service() -> ScopedFolderSandboxMountService:
    """Return global ScopedFolderSandboxMountService singleton instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ScopedFolderSandboxMountService()
    return _service_instance
