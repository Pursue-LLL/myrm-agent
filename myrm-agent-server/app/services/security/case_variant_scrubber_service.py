"""
[POS] app/services/security/case_variant_scrubber_service.py
[INPUT] myrm_agent_harness.core.security.case_variant_scrubber, app.schemas.case_variant_scrubber
[OUTPUT] CaseVariantScrubberService, get_case_variant_scrubber_service

Domain service mediating requests for case-variant credential scrubbing
and declarative OAuth 2.0 PKCE external provider integration.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.case_variant_scrubber import (
    CaseVariantScrubberSuite,
    OAuthPKCEChallengeMethod,
    OAuthPKCEState,
    OAuthProviderManifest,
    ScrubActionEnum,
    ScrubbedEnvRecord,
)

from app.schemas.case_variant_scrubber import (
    DetectInjectionsRequest,
    DetectInjectionsResponse,
    ExchangePKCETokenRequest,
    ExchangePKCETokenResponse,
    InitiatePKCEFlowRequest,
    InitiatePKCEFlowResponse,
    OAuthPKCEChallengeMethodEnum,
    OAuthProviderManifestResponse,
    RegisterOAuthProviderRequest,
    RegisterOAuthProviderResponse,
    ScrubActionEnumResponse,
    ScrubbedEnvRecordResponse,
    ScrubberSuiteMetricsResponse,
    ScrubEnvironmentRequest,
    ScrubEnvironmentResponse,
)


class CaseVariantScrubberService:
    """Service orchestrating environment credential scrubbing and declarative OAuth PKCE."""

    def __init__(self, suite: CaseVariantScrubberSuite | None = None) -> None:
        self._suite = suite or CaseVariantScrubberSuite()

    def scrub_environment(self, req: ScrubEnvironmentRequest) -> ScrubEnvironmentResponse:
        """Deeply scrub environment dictionary against case-variant and delimiter leaks."""
        action = ScrubActionEnum(req.action.value)
        whitelist_set = set(req.whitelist) if req.whitelist else None

        clean_env, report = self._suite.scrub_environment(
            env_dict=req.env_dict,
            action=action,
            whitelist=whitelist_set,
        )

        records = [self._to_record_response(r) for r in report.scrubbed_records]

        return ScrubEnvironmentResponse(
            clean_env=clean_env,
            total_scanned=report.total_scanned,
            total_dropped=report.total_dropped,
            total_redacted=report.total_redacted,
            scrubbed_records=records,
            detected_injections=list(report.detected_injections),
            timestamp=report.timestamp,
        )

    def detect_injections(self, req: DetectInjectionsRequest) -> DetectInjectionsResponse:
        """Detect intentional mixed-case or delimiter-modified credential injection vectors."""
        suspicious = self._suite.detect_injections(req.env_dict)
        return DetectInjectionsResponse(
            suspicious_keys=suspicious,
            has_injection_risk=len(suspicious) > 0,
        )

    def initiate_pkce_flow(self, req: InitiatePKCEFlowRequest) -> InitiatePKCEFlowResponse:
        """Initiate OAuth 2.0 PKCE challenge flow and generate browser redirect URL."""
        state: OAuthPKCEState
        auth_url: str
        state, auth_url = self._suite.initiate_pkce_flow(
            provider_id=req.provider_id,
            redirect_uri=req.redirect_uri,
            ttl_seconds=req.ttl_seconds,
        )

        return InitiatePKCEFlowResponse(
            flow_id=state.flow_id,
            provider_id=state.provider_id,
            state_token=state.state_token,
            code_challenge=state.code_challenge,
            challenge_method=OAuthPKCEChallengeMethodEnum(state.challenge_method.value),
            authorization_url=auth_url,
            expires_at=state.expires_at,
        )

    def exchange_pkce_token(self, req: ExchangePKCETokenRequest) -> ExchangePKCETokenResponse:
        """Validate PKCE invariants and return payload for upstream token exchange."""
        payload = self._suite.exchange_pkce_token(
            flow_id=req.flow_id,
            auth_code=req.code,
            incoming_state=req.state,
        )

        return ExchangePKCETokenResponse(
            token_endpoint=payload["token_endpoint"],
            client_id=payload["client_id"],
            grant_type=payload["grant_type"],
            code=payload["code"],
            code_verifier=payload["code_verifier"],
            provider_id=payload["provider_id"],
        )

    def register_provider(
        self, req: RegisterOAuthProviderRequest
    ) -> RegisterOAuthProviderResponse:
        """Register third-party declarative OAuth provider manifest."""
        manifest = OAuthProviderManifest(
            provider_id=req.provider_id,
            display_name=req.display_name,
            authorization_endpoint=req.authorization_endpoint,
            token_endpoint=req.token_endpoint,
            client_id=req.client_id,
            scopes=tuple(req.scopes),
            challenge_method=OAuthPKCEChallengeMethod(req.challenge_method.value),
        )
        self._suite.register_oauth_provider(manifest)
        manifest_res = self._to_provider_response(manifest)
        return RegisterOAuthProviderResponse(
            provider=manifest_res,
            message=f"Successfully registered OAuth provider '{manifest.provider_id}'",
        )

    def list_providers(self) -> list[OAuthProviderManifestResponse]:
        """List all currently registered OAuth provider manifests."""
        return [self._to_provider_response(p) for p in self._suite.list_oauth_providers()]

    def get_metrics(self) -> ScrubberSuiteMetricsResponse:
        """Fetch cumulative operational metrics."""
        m = self._suite.metrics
        return ScrubberSuiteMetricsResponse(
            envs_scrubbed_total=m.envs_scrubbed_total,
            credentials_intercepted_total=m.credentials_intercepted_total,
            injections_detected_total=m.injections_detected_total,
            pkce_flows_initiated_total=m.pkce_flows_initiated_total,
            pkce_tokens_exchanged_total=m.pkce_tokens_exchanged_total,
        )

    @staticmethod
    def _to_record_response(rec: ScrubbedEnvRecord) -> ScrubbedEnvRecordResponse:
        return ScrubbedEnvRecordResponse(
            original_key=rec.original_key,
            folded_key=rec.folded_key,
            action=ScrubActionEnumResponse(rec.action.value),
            matched_pattern=rec.matched_pattern,
            redacted_value=rec.redacted_value,
        )

    @staticmethod
    def _to_provider_response(manifest: OAuthProviderManifest) -> OAuthProviderManifestResponse:
        return OAuthProviderManifestResponse(
            provider_id=manifest.provider_id,
            display_name=manifest.display_name,
            authorization_endpoint=manifest.authorization_endpoint,
            token_endpoint=manifest.token_endpoint,
            client_id=manifest.client_id,
            scopes=list(manifest.scopes),
            challenge_method=OAuthPKCEChallengeMethodEnum(manifest.challenge_method.value),
        )


_default_service: CaseVariantScrubberService | None = None


def get_case_variant_scrubber_service() -> CaseVariantScrubberService:
    """Dependency injection provider for CaseVariantScrubberService."""
    global _default_service
    if _default_service is None:
        _default_service = CaseVariantScrubberService()
    return _default_service
