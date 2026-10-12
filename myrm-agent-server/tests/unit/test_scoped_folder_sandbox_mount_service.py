"""Unit tests for ScopedFolderSandboxMountService."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.scoped_folder_sandbox_mount import (
    ScopedFolderGrantRequest,
    ValidatePathSecurityRequest,
)
from app.services.security.scoped_folder_sandbox_mount_service import (
    ScopedFolderSandboxMountService,
    get_scoped_folder_mount_service,
)


@pytest.fixture
def service() -> ScopedFolderSandboxMountService:
    return ScopedFolderSandboxMountService()


def test_singleton_getter() -> None:
    svc1 = get_scoped_folder_mount_service()
    svc2 = get_scoped_folder_mount_service()
    assert svc1 is svc2


def test_validate_path_security(service: ScopedFolderSandboxMountService) -> None:
    # 1. Prohibited sensitive path
    req_bad = ValidatePathSecurityRequest(path="/etc")
    res_bad = service.validate_path_security(req_bad)
    assert res_bad.is_blocked is True
    assert "SYSTEM_PREFIX" in (res_bad.matched_rule or "")

    # 2. Benign path
    req_good = ValidatePathSecurityRequest(path="/tmp")
    res_good = service.validate_path_security(req_good)
    # /tmp is benign work path
    assert res_good.is_blocked is False


def test_grant_folder_access_lifecycle(
    service: ScopedFolderSandboxMountService,
    tmp_path: Path,
) -> None:
    test_folder = tmp_path / "MyProjectData"
    test_folder.mkdir()

    req = ScopedFolderGrantRequest(
        folder_path=str(test_folder),
        access_mode="READ_ONLY",
        lifecycle="EPHEMERAL_PER_SESSION",
        lease_seconds=1800.0,
        alias_slug="project_data",
    )

    # 1. Grant access
    grant = service.grant_folder_access(req)
    assert grant.grant_id.startswith("grant-")
    assert grant.alias_slug == "project_data"
    assert grant.sandbox_mount_path == "/workspace/granted/project_data"
    assert grant.is_revoked is False

    # 2. Query mount spec
    spec = service.get_mount_spec(grant.grant_id)
    assert spec is not None
    assert spec.read_only is True
    assert spec.sandbox_target_path == "/workspace/granted/project_data"

    # 3. List active grants
    active_grants = service.list_active_grants()
    assert any(g.grant_id == grant.grant_id for g in active_grants)

    # 4. Revoke grant
    rev_res = service.revoke_grant(grant.grant_id)
    assert rev_res.revoked is True

    # 5. Verify mount spec is gone
    assert service.get_mount_spec(grant.grant_id) is None
