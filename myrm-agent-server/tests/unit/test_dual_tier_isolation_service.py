"""Unit test for DualTierIsolationService.

[INPUT]
- RegisterAdminKeyRequest, DeriveUserKeyRequest, EvaluateAccessRequest.

[OUTPUT]
- Verified behavior of admin key registration, user key derivation, and dual-tier isolation evaluation.

[POS]
- Server unit test layer for dual-tier root admin and user API key isolation.
"""

from __future__ import annotations

from app.schemas.dual_tier_isolation import (
    DeriveUserKeyRequest,
    EvaluateAccessRequest,
    RegisterAdminKeyRequest,
)
from app.services.security.dual_tier_isolation_service import (
    DualTierIsolationService,
)


def test_service_register_admin_and_evaluate() -> None:
    service = DualTierIsolationService()

    # 1. Register admin key
    reg_req = RegisterAdminKeyRequest(allowed_scopes=["admin:*", "sandbox:schedule"])
    adm_dto = service.register_admin_key(reg_req)

    assert adm_dto.raw_key.startswith("myrm_adm_")
    assert adm_dto.tier == "ROOT_ADMIN"

    # 2. Evaluate admin on control plane -> Permitted
    eval_cp = service.evaluate_access(
        EvaluateAccessRequest(
            raw_key=adm_dto.raw_key,
            requested_plane="CONTROL_PLANE",
        )
    )
    assert eval_cp.is_permitted is True
    assert eval_cp.verdict == "PERMITTED"
    assert eval_cp.effective_tier == "ROOT_ADMIN"

    # 3. Evaluate admin directly on tenant data plane -> Blocked (Physical Isolation)
    eval_dp = service.evaluate_access(
        EvaluateAccessRequest(
            raw_key=adm_dto.raw_key,
            requested_plane="DATA_PLANE",
            target_user_id="user_target_123",
        )
    )
    assert eval_dp.is_permitted is False
    assert eval_dp.verdict == "BLOCKED_DATA_PLANE_VIOLATION"


def test_service_derive_user_key_and_evaluate() -> None:
    service = DualTierIsolationService()

    # 1. Derive user key
    derive_req = DeriveUserKeyRequest(
        user_id="alice",
        tenant_id="tenant_org_alpha",
        allowed_scopes=["data:*"],
    )
    usr_dto = service.derive_user_key(derive_req)

    assert usr_dto.raw_key.startswith("myrm_usr_")
    assert usr_dto.tier == "DERIVED_USER"
    assert usr_dto.user_id == "alice"
    assert usr_dto.tenant_id == "tenant_org_alpha"

    # 2. Evaluate user on own data plane -> Permitted
    eval_own = service.evaluate_access(
        EvaluateAccessRequest(
            raw_key=usr_dto.raw_key,
            requested_plane="DATA_PLANE",
            target_user_id="alice",
            target_tenant_id="tenant_org_alpha",
        )
    )
    assert eval_own.is_permitted is True
    assert eval_own.verdict == "PERMITTED"

    # 3. Evaluate user on another user's data plane -> Cross-Tenant Breach Blocked
    eval_breach = service.evaluate_access(
        EvaluateAccessRequest(
            raw_key=usr_dto.raw_key,
            requested_plane="DATA_PLANE",
            target_user_id="bob",
        )
    )
    assert eval_breach.is_permitted is False
    assert eval_breach.verdict == "BLOCKED_CROSS_TENANT_BREACH"

    # 4. Evaluate user on control plane -> Blocked
    eval_cp = service.evaluate_access(
        EvaluateAccessRequest(
            raw_key=usr_dto.raw_key,
            requested_plane="CONTROL_PLANE",
        )
    )
    assert eval_cp.is_permitted is False
    assert eval_cp.verdict == "BLOCKED_CONTROL_PLANE_VIOLATION"
