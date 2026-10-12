"""Unit tests for DirectoryTrustGateService in myrm-agent-server."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.core.security.directory_trust_gate import DirectoryTrustStore

from app.schemas.directory_trust_gate import (
    ProjectMemoryConfigDto,
    ResolveDirectoryTrustRequest,
    TrustDirectoryRequest,
    UntrustDirectoryRequest,
)
from app.services.security.directory_trust_gate_service import (
    DirectoryTrustGateService,
    get_directory_trust_gate_service,
)


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def service() -> DirectoryTrustGateService:
    trust_store = DirectoryTrustStore()
    return DirectoryTrustGateService(trust_store=trust_store)


def test_trust_and_untrust_directory_flow(
    service: DirectoryTrustGateService, temp_dir: str
) -> None:
    target = str(Path(temp_dir) / "project_a")
    Path(target).mkdir(parents=True, exist_ok=True)

    # 1. Trust directory
    trust_resp = service.trust_directory(TrustDirectoryRequest(directory=target))
    assert trust_resp.trusted is True
    assert trust_resp.canonical_path == str(Path(target).resolve())

    # 2. List trusted directories
    list_resp = service.list_trusted()
    assert list_resp.count >= 1
    assert trust_resp.canonical_path in list_resp.trusted_directories

    # 3. Untrust directory
    untrust_resp = service.untrust_directory(UntrustDirectoryRequest(directory=target))
    assert untrust_resp.removed is True

    # 4. Verify removal
    list_after = service.list_trusted()
    assert trust_resp.canonical_path not in list_after.trusted_directories


def test_resolve_directory_trust_untrusted_drops_remote(
    service: DirectoryTrustGateService, temp_dir: str
) -> None:
    cloned_repo = str(Path(temp_dir) / "untrusted_cloned_repo")
    Path(cloned_repo).mkdir(parents=True, exist_ok=True)

    # Attempting to supply both remote_url and remote_token from untrusted cloned repo
    req = ResolveDirectoryTrustRequest(
        start_directory=cloned_repo,
        config_override=ProjectMemoryConfigDto(
            scope="team_scope",
            remote_url="https://malicious-external-host.com/memory",
            remote_token="stolen_or_malicious_token_123",
        ),
    )

    resolved = service.resolve_directory_trust(req)
    assert resolved.is_directory_trusted is False
    assert resolved.decision == "UNTRUSTED_REMOTE_REFUSED"
    # Remote credentials must be strictly dropped
    assert resolved.remote_url is None
    assert resolved.remote_token is None
    assert resolved.refusal_notice is not None
    assert "[MYRM_SECURITY]" in resolved.refusal_notice


def test_resolve_directory_trust_trusted_allows_remote(
    service: DirectoryTrustGateService, temp_dir: str
) -> None:
    trusted_project = str(Path(temp_dir) / "legit_trusted_repo")
    Path(trusted_project).mkdir(parents=True, exist_ok=True)

    # Explicitly trust the project
    service.trust_directory(TrustDirectoryRequest(directory=trusted_project))

    req = ResolveDirectoryTrustRequest(
        start_directory=trusted_project,
        config_override=ProjectMemoryConfigDto(
            scope="production_scope",
            remote_url="https://vault.internal.corp/memory",
            remote_token="valid_corp_token_999",
        ),
    )

    resolved = service.resolve_directory_trust(req)
    assert resolved.is_directory_trusted is True
    assert resolved.decision == "TRUSTED_AUTHORIZED"
    assert resolved.remote_url == "https://vault.internal.corp/memory"
    assert resolved.remote_token == "valid_corp_token_999"
    assert resolved.refusal_notice is None


def test_get_directory_trust_gate_service_singleton() -> None:
    svc1 = get_directory_trust_gate_service()
    svc2 = get_directory_trust_gate_service()
    assert svc1 is svc2
