"""Unit test for LlmEgressGuardService.

[INPUT]
- SetLlmEgressPolicyRequest, EvaluateLlmEgressRequest.

[OUTPUT]
- Verified behavior of fail-closed egress validation, domain allowlists, and credential binding.

[POS]
- Server unit test layer for fail-closed LLM egress gating.
"""

from __future__ import annotations

from app.schemas.llm_egress_guard import (
    DomainAllowlistRuleDto,
    EvaluateLlmEgressRequest,
    SetLlmEgressPolicyRequest,
)
from app.services.security.llm_egress_guard_service import (
    LlmEgressGuardService,
)


def test_service_fail_closed_when_no_policy() -> None:
    service = LlmEgressGuardService()
    service.clear_policy()

    req = EvaluateLlmEgressRequest(
        target_url_or_domain="https://api.openai.com/v1/chat/completions",
        presented_credential_id="any-token",
    )
    res = service.evaluate_egress(req)

    assert res.is_permitted is False
    assert res.verdict == "BLOCKED_NO_POLICY"
    assert "no explicit egress policy is active" in res.rationale


def test_service_set_policy_and_evaluate() -> None:
    service = LlmEgressGuardService()

    policy_req = SetLlmEgressPolicyRequest(
        policy_id="pol-corp-prod",
        allowed_rules=[
            DomainAllowlistRuleDto(
                rule_id="RULE-OPENAI",
                domain_pattern="api.openai.com",
                bound_credential_ids=["cred-openai-key"],
                require_credential_binding=True,
            ),
            DomainAllowlistRuleDto(
                rule_id="RULE-AZURE-WILDCARD",
                domain_pattern="*.openai.azure.com",
                bound_credential_ids=["cred-azure-key"],
                require_credential_binding=False,
            ),
        ],
        is_default_deny=True,
    )
    policy_dto = service.set_policy(policy_req)
    assert policy_dto.policy_id == "pol-corp-prod"
    assert len(policy_dto.allowed_rules) == 2

    # 1. Permitted with correct credential
    res_ok = service.evaluate_egress(
        EvaluateLlmEgressRequest(
            target_url_or_domain="https://api.openai.com/v1/models",
            presented_credential_id="cred-openai-key",
        )
    )
    assert res_ok.is_permitted is True
    assert res_ok.verdict == "PERMITTED"
    assert res_ok.domain == "api.openai.com"

    # 2. Blocked due to credential mismatch
    res_mismatch = service.evaluate_egress(
        EvaluateLlmEgressRequest(
            target_url_or_domain="https://api.openai.com/v1/models",
            presented_credential_id="cred-stolen-token",
        )
    )
    assert res_mismatch.is_permitted is False
    assert res_mismatch.verdict == "BLOCKED_CREDENTIAL_MISMATCH"

    # 3. Blocked domain not in allowlist (Default-Deny)
    res_blocked_domain = service.evaluate_egress(
        EvaluateLlmEgressRequest(
            target_url_or_domain="https://unknown-llm-proxy.io/v1",
            presented_credential_id="cred-openai-key",
        )
    )
    assert res_blocked_domain.is_permitted is False
    assert res_blocked_domain.verdict == "BLOCKED_DOMAIN_NOT_ALLOWED"


def test_service_clear_policy_reverts_to_fail_closed() -> None:
    service = LlmEgressGuardService()

    service.set_policy(
        SetLlmEgressPolicyRequest(
            policy_id="temp-pol",
            allowed_rules=[
                DomainAllowlistRuleDto(
                    rule_id="R1",
                    domain_pattern="api.deepseek.com",
                    bound_credential_ids=["k1"],
                    require_credential_binding=False,
                )
            ],
        )
    )
    assert service.get_policy() is not None

    service.clear_policy()
    assert service.get_policy() is None

    res = service.evaluate_egress(
        EvaluateLlmEgressRequest(target_url_or_domain="https://api.deepseek.com")
    )
    assert res.is_permitted is False
    assert res.verdict == "BLOCKED_NO_POLICY"
