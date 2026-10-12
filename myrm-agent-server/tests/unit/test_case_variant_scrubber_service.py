"""
[POS] tests/unit/test_case_variant_scrubber_service.py
[INPUT] pytest, app.schemas.case_variant_scrubber, app.services.security.case_variant_scrubber_service
[OUTPUT] Unit tests for CaseVariantScrubberService

Validates service-level case-variant credential scrubbing, injection detection,
and declarative OAuth 2.0 PKCE lifecycle flows.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.case_variant_scrubber import (
    DetectInjectionsRequest,
    ExchangePKCETokenRequest,
    InitiatePKCEFlowRequest,
    OAuthPKCEChallengeMethodEnum,
    RegisterOAuthProviderRequest,
    ScrubActionEnumResponse,
    ScrubEnvironmentRequest,
)
from app.services.security.case_variant_scrubber_service import (
    CaseVariantScrubberService,
)


def test_service_scrub_environment() -> None:
    """Validate environment scrubbing with drop and redaction modes."""
    service = CaseVariantScrubberService()

    raw_env = {
        "Openai_Api_Key": "sk-proj-1234",
        "GITHUB_TOKEN": "ghp-5678",
        "USER": "developer",
        "PATH": "/usr/local/bin",
    }

    # 1. DROP mode
    drop_res = service.scrub_environment(
        ScrubEnvironmentRequest(
            env_dict=raw_env,
            action=ScrubActionEnumResponse.DROP,
        )
    )
    assert drop_res.total_dropped == 2
    assert "Openai_Api_Key" not in drop_res.clean_env
    assert "GITHUB_TOKEN" not in drop_res.clean_env
    assert drop_res.clean_env["USER"] == "developer"
    assert "Openai_Api_Key" in drop_res.detected_injections

    # 2. REDACT mode
    redact_res = service.scrub_environment(
        ScrubEnvironmentRequest(
            env_dict=raw_env,
            action=ScrubActionEnumResponse.REDACT_PLACEHOLDER,
        )
    )
    assert redact_res.total_redacted == 2
    assert redact_res.clean_env["Openai_Api_Key"] == "[REDACTED_BY_SCRUBBER]"
    assert redact_res.clean_env["GITHUB_TOKEN"] == "[REDACTED_BY_SCRUBBER]"


def test_service_detect_injections() -> None:
    """Validate injection probe detection."""
    service = CaseVariantScrubberService()

    probe_res = service.detect_injections(
        DetectInjectionsRequest(
            env_dict={
                "openai-api-key": "secret",
                "NORMAL_VAR": "val",
            }
        )
    )
    assert probe_res.has_injection_risk is True
    assert "openai-api-key" in probe_res.suspicious_keys


def test_service_pkce_flow_and_provider_registry() -> None:
    """Validate PKCE flow initiation, token exchange preparation, and provider registration."""
    service = CaseVariantScrubberService()

    # 1. Register custom provider
    reg_res = service.register_provider(
        RegisterOAuthProviderRequest(
            provider_id="custom_ai_provider",
            display_name="Custom AI Provider",
            authorization_endpoint="https://ai.example.com/oauth/authorize",
            token_endpoint="https://ai.example.com/oauth/token",
            client_id="myrm-client-001",
            scopes=["model:read", "inference:write"],
            challenge_method=OAuthPKCEChallengeMethodEnum.S256,
        )
    )
    assert reg_res.provider.provider_id == "custom_ai_provider"

    # 2. List providers
    providers = service.list_providers()
    assert any(p.provider_id == "custom_ai_provider" for p in providers)

    # 3. Initiate PKCE
    init_res = service.initiate_pkce_flow(
        InitiatePKCEFlowRequest(
            provider_id="custom_ai_provider",
            redirect_uri="https://localhost:3000/callback",
        )
    )
    assert init_res.flow_id.startswith("flow-")
    assert "client_id=myrm-client-001" in init_res.authorization_url

    # 4. Exchange PKCE
    exch_res = service.exchange_pkce_token(
        ExchangePKCETokenRequest(
            flow_id=init_res.flow_id,
            code="auth_code_999",
            state=init_res.state_token,
        )
    )
    assert exch_res.code == "auth_code_999"
    assert exch_res.grant_type == "authorization_code"
    assert exch_res.code_verifier != ""

    # 5. Metrics
    metrics = service.get_metrics()
    assert metrics.pkce_flows_initiated_total >= 1
    assert metrics.pkce_tokens_exchanged_total >= 1
