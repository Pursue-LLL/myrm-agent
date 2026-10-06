"""Service layer for Enterprise Zero-Credential Outbound Proxy and Super-CLI Suite.

[INPUT]
- myrm_agent_harness.core.security.zero_credential_proxy::{AuthHeaderScheme, OutboundProxyRequest, ProxyInjectionRule, RedactionSanitizationGate, SuperCliCommandSpec, SuperCliWrapper, ZeroCredentialOutboundProxy}
- app.schemas.zero_credential_proxy::{AuthHeaderSchemeEnum, OutboundProxyRelayRequest, OutboundProxyRelayResponse, ProxyRuleMetadataResponse, RegisterProxyRuleRequest, SanitizeTextRequest, SanitizeTextResponse, SuperCliExecuteRequest, SuperCliExecuteResponse}

[OUTPUT]
- ZeroCredentialProxyService: singleton service coordinating zero-credential outbound proxy, redaction gate, and Super-CLI.

[POS]
app/services/security service wrapping harness zero credential proxy and super CLI tools.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.core.security.zero_credential_proxy import (
    AuthHeaderScheme,
    OutboundProxyRequest,
    ProxyInjectionRule,
    RedactionSanitizationGate,
    SuperCliCommandSpec,
    SuperCliWrapper,
    ZeroCredentialOutboundProxy,
)

from app.schemas.zero_credential_proxy import (
    AuthHeaderSchemeEnum,
    OutboundProxyRelayRequest,
    OutboundProxyRelayResponse,
    ProxyRuleMetadataResponse,
    RegisterProxyRuleRequest,
    SanitizeTextRequest,
    SanitizeTextResponse,
    SuperCliExecuteRequest,
    SuperCliExecuteResponse,
)

logger = logging.getLogger(__name__)


class ZeroCredentialProxyService:
    """Business service coordinating zero-credential outbound proxy, redaction gate, and Super-CLI."""

    _instance: ClassVar[ZeroCredentialProxyService | None] = None

    def __init__(
        self,
        proxy: ZeroCredentialOutboundProxy | None = None,
        redaction_gate: RedactionSanitizationGate | None = None,
        super_cli: SuperCliWrapper | None = None,
    ) -> None:
        self._redaction_gate = redaction_gate or RedactionSanitizationGate()
        self._proxy = proxy or ZeroCredentialOutboundProxy(
            redaction_gate=self._redaction_gate
        )
        self._super_cli = super_cli or SuperCliWrapper(
            redaction_gate=self._redaction_gate
        )

    @classmethod
    def get_instance(cls) -> ZeroCredentialProxyService:
        """Obtain singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def register_rule(
        self, request: RegisterProxyRuleRequest
    ) -> ProxyRuleMetadataResponse:
        """Register a new proxy injection rule."""
        scheme_map = {
            AuthHeaderSchemeEnum.BEARER: AuthHeaderScheme.BEARER,
            AuthHeaderSchemeEnum.BASIC: AuthHeaderScheme.BASIC,
            AuthHeaderSchemeEnum.CUSTOM: AuthHeaderScheme.CUSTOM,
        }
        rule = ProxyInjectionRule(
            rule_id=request.rule_id,
            target_domain=request.target_domain,
            real_token=request.real_token,
            header_name=request.header_name,
            scheme=scheme_map[request.scheme],
            custom_header_prefix=request.custom_header_prefix,
            description=request.description,
        )
        self._proxy.register_rule(rule)
        return ProxyRuleMetadataResponse(
            rule_id=rule.rule_id,
            target_domain=rule.target_domain,
            real_token="[REDACTED_IN_VAULT]",
            header_name=rule.header_name,
            scheme=request.scheme,
            custom_header_prefix=rule.custom_header_prefix,
            description=rule.description,
        )

    def list_rules(self) -> list[ProxyRuleMetadataResponse]:
        """List all active proxy rules with redacted secrets."""
        rules = self._proxy.list_rules()
        return [
            ProxyRuleMetadataResponse(
                rule_id=r.rule_id,
                target_domain=r.target_domain,
                real_token="[REDACTED_IN_VAULT]",
                header_name=r.header_name,
                scheme=AuthHeaderSchemeEnum(r.scheme.value),
                custom_header_prefix=r.custom_header_prefix,
                description=r.description,
            )
            for r in rules
        ]

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an existing proxy rule."""
        self._proxy.remove_rule(rule_id)
        return True

    def relay_outbound_request(
        self, request: OutboundProxyRelayRequest
    ) -> OutboundProxyRelayResponse:
        """Process sandbox request, injecting credential at host boundary."""
        harness_req = OutboundProxyRequest(
            url=request.url,
            method=request.method,
            headers=request.headers,
            body=request.body,
            connector_ref=request.connector_ref,
        )
        resp = self._proxy.process_request(harness_req)
        return OutboundProxyRelayResponse(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=resp.body,
            credential_injected=resp.credential_injected,
            matched_rule_id=resp.matched_rule_id,
            redacted_count=resp.redacted_count,
            transparency_notice=resp.transparency_notice,
            blocked_reason=resp.blocked_reason,
        )

    def sanitize_text(self, request: SanitizeTextRequest) -> SanitizeTextResponse:
        """Scan text and redact sensitive credentials with model transparency."""
        gate = (
            self._redaction_gate
            if request.inject_notice
            else RedactionSanitizationGate(inject_notice=False)
        )
        res = gate.sanitize(request.text)
        return SanitizeTextResponse(
            sanitized_text=res.sanitized_text,
            redacted_count=res.redacted_count,
            transparency_notice=res.transparency_notice,
            matched_patterns=res.matched_patterns,
        )

    def execute_super_cli(
        self, request: SuperCliExecuteRequest
    ) -> SuperCliExecuteResponse:
        """Execute a target CLI command with memory-only token injection and sanitized streams."""
        spec = SuperCliCommandSpec(
            target_cli=request.target_cli,
            args=request.args,
            injected_env=request.injected_env,
            timeout_seconds=request.timeout_seconds,
        )
        res = self._super_cli.execute_command(spec)
        return SuperCliExecuteResponse(
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            redacted_count=res.redacted_count,
            transparency_notice=res.transparency_notice,
        )
