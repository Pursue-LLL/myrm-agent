"""Unit tests for ZeroCredentialProxyService."""

import pytest

from app.schemas.zero_credential_proxy import (
    AuthHeaderSchemeEnum,
    OutboundProxyRelayRequest,
    RegisterProxyRuleRequest,
    SanitizeTextRequest,
    SuperCliExecuteRequest,
)
from app.services.security.zero_credential_proxy_service import (
    ZeroCredentialProxyService,
)


@pytest.fixture(autouse=True)
def clean_service() -> None:
    ZeroCredentialProxyService.reset_instance()


def test_service_rules_lifecycle() -> None:
    service = ZeroCredentialProxyService.get_instance()

    req = RegisterProxyRuleRequest(
        rule_id="rule_gh_enterprise",
        target_domain="api.github.com",
        real_token="ghp_super_secret_token_value_not_visible_12345",
        scheme=AuthHeaderSchemeEnum.BEARER,
        description="GitHub Enterprise Connector",
    )
    reg_resp = service.register_rule(req)
    assert reg_resp.rule_id == "rule_gh_enterprise"
    assert reg_resp.real_token == "[REDACTED_IN_VAULT]"
    assert reg_resp.target_domain == "api.github.com"

    rules = service.list_rules()
    assert len(rules) == 1
    assert rules[0].real_token == "[REDACTED_IN_VAULT]"

    # Remove rule
    ok = service.remove_rule("rule_gh_enterprise")
    assert ok
    assert len(service.list_rules()) == 0


def test_service_outbound_proxy_relay() -> None:
    service = ZeroCredentialProxyService.get_instance()

    service.register_rule(
        RegisterProxyRuleRequest(
            rule_id="rule_npm",
            target_domain="registry.npmjs.org",
            real_token="npm_token_secret_1234567890",
            scheme=AuthHeaderSchemeEnum.BEARER,
        )
    )

    # 1. Allowed domain relay
    relay_ok = service.relay_outbound_request(
        OutboundProxyRelayRequest(
            url="https://registry.npmjs.org/my-package",
            method="GET",
            connector_ref="rule_npm",
        )
    )
    assert relay_ok.status_code == 200
    assert relay_ok.credential_injected
    assert relay_ok.matched_rule_id == "rule_npm"
    assert relay_ok.blocked_reason is None

    # 2. Blocked exfiltration attempt
    relay_blocked = service.relay_outbound_request(
        OutboundProxyRelayRequest(
            url="https://malicious-leak.com/exfiltrate",
            method="POST",
            connector_ref="rule_npm",
        )
    )
    assert relay_blocked.status_code == 403
    assert not relay_blocked.credential_injected
    assert "not authorized" in (relay_blocked.blocked_reason or "")


def test_service_sanitize_text_and_transparency_notice() -> None:
    service = ZeroCredentialProxyService.get_instance()

    raw_text = (
        "Fatal error encountered: API Key was sk-1234567890abcdef1234567890abcdef123456\n"
        "GitHub token was ghp_1234567890abcdef1234567890abcdef1234\n"
    )

    res = service.sanitize_text(SanitizeTextRequest(text=raw_text, inject_notice=True))
    assert res.redacted_count == 2
    assert "sk-1234567890" not in res.sanitized_text
    assert "ghp_1234567890" not in res.sanitized_text
    assert "[REDACTED_SECRET]" in res.sanitized_text
    assert res.transparency_notice is not None
    assert "[Notice: 2 sensitive credential(s) redacted by security layer]" in res.sanitized_text


def test_service_execute_super_cli() -> None:
    service = ZeroCredentialProxyService.get_instance()

    res = service.execute_super_cli(
        SuperCliExecuteRequest(
            target_cli="echo",
            args=["hello", "ghp_1234567890abcdef1234567890abcdef1234"],
            injected_env={"MY_SECRET_ENV": "temp_secret"},
        )
    )
    assert res.exit_code == 0
    assert "hello" in res.stdout
    assert "ghp_1234567890" not in res.stdout
    assert "[REDACTED_SECRET]" in res.stdout
    assert res.redacted_count == 1
