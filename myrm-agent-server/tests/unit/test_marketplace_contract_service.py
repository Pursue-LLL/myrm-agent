"""Unit tests for MarketplaceContractService."""

from __future__ import annotations

import pytest

from app.schemas.marketplace_contract import (
    AdmissionPolicyDto,
    CapabilityContractDto,
    EvaluateAdmissionRequest,
    MarketplaceManifestItemDto,
    UpdateAdmissionPolicyRequest,
    ValidateManifestRequest,
)
from app.services.security.marketplace_contract_service import (
    MarketplaceContractService,
)


@pytest.fixture
def sample_service() -> MarketplaceContractService:
    return MarketplaceContractService()


@pytest.fixture
def sample_manifest_dto() -> MarketplaceManifestItemDto:
    return MarketplaceManifestItemDto(
        package_id="metamask-wallet",
        name="MetaMask Wallet Mod",
        version="1.0.0",
        repo_url="https://github.com/akugone/hermes-metamask-wallet",
        source_sha="b56d6bbf575391d172280016abf778d31c5ca8bd",
        tier="COMMUNITY",
        requires_host=">=0.21.0",
        platforms=["macos", "linux"],
        capabilities=CapabilityContractDto(
            provides_tools=["mm_status", "mm_balance"],
            provides_hooks=["pre_tool_call"],
            requires_env=["METAMASK_RPC_URL"],
        ),
        publisher="akugone",
    )


def test_validate_manifest_valid_and_invalid(
    sample_service: MarketplaceContractService,
    sample_manifest_dto: MarketplaceManifestItemDto,
) -> None:
    # 1. Valid manifest
    req_valid = ValidateManifestRequest(
        manifest=sample_manifest_dto,
        target_platform="macos",
    )
    res_valid = sample_service.validate_manifest(req_valid)
    assert res_valid.is_valid is True
    assert res_valid.platform_supported is True
    assert res_valid.error_message is None

    # 2. Unsupported platform
    req_windows = ValidateManifestRequest(
        manifest=sample_manifest_dto,
        target_platform="windows",
    )
    res_windows = sample_service.validate_manifest(req_windows)
    assert res_windows.is_valid is True
    assert res_windows.platform_supported is False

    # 3. Invalid mutable tag instead of commit SHA
    bad_manifest = sample_manifest_dto.model_copy(update={"source_sha": "main"})
    req_bad = ValidateManifestRequest(
        manifest=bad_manifest,
        target_platform="macos",
    )
    res_bad = sample_service.validate_manifest(req_bad)
    assert res_bad.is_valid is False
    assert res_bad.error_message is not None
    assert "must specify an immutable commit" in res_bad.error_message


def test_evaluate_admission_allowed_and_blocked(
    sample_service: MarketplaceContractService,
    sample_manifest_dto: MarketplaceManifestItemDto,
) -> None:
    # By default, open policy with strict pinning passes
    eval_req = EvaluateAdmissionRequest(manifest=sample_manifest_dto)
    eval_res = sample_service.evaluate_admission(eval_req)
    assert eval_res.is_admitted is True
    assert eval_res.verdict.is_admitted is True

    # Update policy to require OFFICIAL tier
    sample_service.update_policy(
        UpdateAdmissionPolicyRequest(
            policy=AdmissionPolicyDto(
                allowed_tiers=["OFFICIAL", "VERIFIED"],
                enforce_strict_pinning=True,
            )
        )
    )

    eval_blocked = sample_service.evaluate_admission(eval_req)
    assert eval_blocked.is_admitted is False
    assert eval_blocked.verdict.is_admitted is False
    assert any("Tier 'COMMUNITY' is disallowed" in v for v in eval_blocked.verdict.violations)


def test_policy_crud_lifecycle(sample_service: MarketplaceContractService) -> None:
    current = sample_service.get_policy()
    assert current.enforce_strict_pinning is True

    updated = sample_service.update_policy(
        UpdateAdmissionPolicyRequest(
            policy=AdmissionPolicyDto(
                allowed_sources=["https://github.com/my-corp/"],
                allowed_tiers=["OFFICIAL"],
                disallowed_capabilities=["malicious_tool"],
                enforce_strict_pinning=True,
            )
        )
    )
    assert updated.allowed_sources == ["https://github.com/my-corp/"]
    assert updated.allowed_tiers == ["OFFICIAL"]
    assert updated.disallowed_capabilities == ["malicious_tool"]
