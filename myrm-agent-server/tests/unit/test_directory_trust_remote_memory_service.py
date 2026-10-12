"""Unit tests for DirectoryTrustRemoteMemoryService.

[INPUT]
- TrustDirectoryRequest, ResolveProjectRemoteRequest.

[OUTPUT]
- Verified service layer logic for directory trust and project remote memory gating.

[POS]
- Server unit test layer for remote memory directory trust gating.
"""

from __future__ import annotations

import os
import tempfile

from app.schemas.directory_trust_remote_memory import (
    ProjectMemoryConfigDto,
    ResolveProjectRemoteRequest,
    TrustDirectoryRequest,
)
from app.services.security.directory_trust_remote_memory_service import (
    DirectoryTrustRemoteMemoryService,
)


def test_service_trust_lifecycle() -> None:
    service = DirectoryTrustRemoteMemoryService()
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Initial check is untrusted
        check_before = service.check_directory_trust(tmpdir)
        assert check_before.is_trusted is False

        # 2. Trust directory
        trust_res = service.set_directory_trust(
            TrustDirectoryRequest(directory=tmpdir, action="trust")
        )
        assert trust_res.is_trusted is True
        assert trust_res.action == "trust"

        # 3. Check again
        check_after = service.check_directory_trust(tmpdir)
        assert check_after.is_trusted is True
        assert len(service.list_trusted_directories()) >= 1

        # 4. Untrust directory
        untrust_res = service.set_directory_trust(
            TrustDirectoryRequest(directory=tmpdir, action="untrust")
        )
        assert untrust_res.is_trusted is False
        assert service.check_directory_trust(tmpdir).is_trusted is False


def test_service_resolve_project_remote_gating() -> None:
    service = DirectoryTrustRemoteMemoryService()
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = os.path.join(tmpdir, ".myrm.yaml")

        req = ResolveProjectRemoteRequest(
            config=ProjectMemoryConfigDto(
                local_scope="scope-analytics",
                domain="analytics",
                remote_url="https://remote-enterprise.corp.com",
                remote_token="corp-token-xyz",
                remote_scopes=["enterprise/analytics"],
            ),
            config_path=cfg_path,
        )

        # 1. Untrusted directory: blocked
        res_blocked = service.resolve_project_remote(req)
        assert res_blocked.is_trusted is False
        assert res_blocked.is_outbound_authorized is False
        assert res_blocked.remote_url is None
        assert res_blocked.refused_from is not None
        assert res_blocked.refusal_notice is not None
        assert "myrm trust" in res_blocked.refusal_notice

        # 2. Trust directory: authorized
        service.set_directory_trust(
            TrustDirectoryRequest(directory=tmpdir, action="trust")
        )
        res_allowed = service.resolve_project_remote(req)
        assert res_allowed.is_trusted is True
        assert res_allowed.is_outbound_authorized is True
        assert res_allowed.remote_url == "https://remote-enterprise.corp.com"
        assert res_allowed.remote_token == "corp-token-xyz"
        assert res_allowed.remote_scopes == ["enterprise/analytics"]
        assert res_allowed.refusal_notice is None
