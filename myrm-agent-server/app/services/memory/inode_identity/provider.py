"""[POS]: app/services/memory/inode_identity/provider.py
[INPUT]: app/schemas/inode_identity.py, myrm_agent_harness/toolkits/memory/inode_identity/
[OUTPUT]: InodeIdentityProvider singleton for directory identity resolution and sync guard.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.inode_identity import (
    DeviceFilesystemKind,
    DirectoryIdentity,
    InodeIdentityFacade,
    get_inode_identity_facade,
)

from app.schemas.inode_identity import (
    DirectoryIdentityDTO,
    ResolveIdentityRequest,
    ResolveIdentityResponse,
    VerifySyncRequest,
    VerifySyncResponse,
)


class InodeIdentityProvider:
    """Service provider adapting harness InodeIdentityFacade to server API layer."""

    def __init__(self, facade: InodeIdentityFacade | None = None) -> None:
        self._facade: InodeIdentityFacade = facade or get_inode_identity_facade()

    def resolve(self, req: ResolveIdentityRequest) -> ResolveIdentityResponse:
        """Resolve physical device and inode identity for requested target directory."""
        res = self._facade.resolve(req.target_path)
        ident_dto: DirectoryIdentityDTO | None = None
        if res.identity is not None:
            ident_dto = self._map_to_dto(res.identity)

        return ResolveIdentityResponse(
            target_path=req.target_path,
            real_path=res.real_path,
            is_accessible=res.is_accessible,
            is_directory=res.is_directory,
            is_symlink=res.is_symlink,
            identity=ident_dto,
            error_message=res.error_message,
        )

    def verify_sync(self, req: VerifySyncRequest) -> VerifySyncResponse:
        """Verify and arbitrate workspace directory identity against known records."""
        known_entities: list[DirectoryIdentity] = []
        for known in req.known_identities:
            fs_kind = DeviceFilesystemKind.POSIX
            if known.fs_kind == "windows":
                fs_kind = DeviceFilesystemKind.WINDOWS
            elif known.fs_kind == "fallback_virtual":
                fs_kind = DeviceFilesystemKind.FALLBACK_VIRTUAL

            known_entities.append(
                DirectoryIdentity(
                    canonical_path=known.canonical_path,
                    device_id=known.device_id,
                    inode_id=known.inode_id,
                    birth_time_ns=known.birth_time_ns,
                    root_signature=known.root_signature,
                    fs_kind=fs_kind,
                )
            )

        decision = self._facade.evaluate_sync(req.target_path, known_entities)
        current_dto: DirectoryIdentityDTO | None = None
        if decision.identity is not None:
            current_dto = self._map_to_dto(decision.identity)

        return VerifySyncResponse(
            action=decision.action.value,
            match_kind=decision.match_kind.value,
            reason=decision.reason,
            old_path=decision.old_path,
            new_path=decision.new_path,
            physical_key=decision.physical_key,
            needs_database_relocation=decision.needs_database_relocation,
            identity=current_dto,
        )

    def _map_to_dto(self, ident: DirectoryIdentity) -> DirectoryIdentityDTO:
        """Convert a domain DirectoryIdentity model to a Pydantic DTO."""
        return DirectoryIdentityDTO(
            canonical_path=ident.canonical_path,
            device_id=ident.device_id,
            inode_id=ident.inode_id,
            birth_time_ns=ident.birth_time_ns,
            root_signature=ident.root_signature,
            fs_kind=ident.fs_kind.value,
            is_symlink=ident.is_symlink,
            physical_key=ident.physical_key,
        )


_PROVIDER_INSTANCE: InodeIdentityProvider | None = None


def get_inode_identity_provider() -> InodeIdentityProvider:
    """Obtain or initialize the global InodeIdentityProvider singleton."""
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is None:
        _PROVIDER_INSTANCE = InodeIdentityProvider()
    return _PROVIDER_INSTANCE
