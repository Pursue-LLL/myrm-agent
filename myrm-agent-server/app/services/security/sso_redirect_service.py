"""Service layer for SSO Redirect Idempotency and Probe Hysteresis.

[INPUT]
- ValidateRedirectTargetRequest, BuildSsoRedirectUrlRequest, EvaluateProbeRequest DTOs.

[OUTPUT]
- ValidateRedirectTargetResponse, BuildSsoRedirectUrlResponse, EvaluateProbeResponse DTOs.

[POS]
- Server service encapsulating IHUI-AI #2728e745 idempotent redirect and probe hysteresis.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.sso_redirect import (
    ProbeEvaluationResult,
    ProbeHysteresisController,
    SsoRedirectBuildResult,
    SsoRedirectValidation,
    SsoUrlSanitizer,
)

from app.schemas.sso_redirect import (
    BuildSsoRedirectUrlRequest,
    BuildSsoRedirectUrlResponse,
    EvaluateProbeRequest,
    EvaluateProbeResponse,
    UrlPathCategoryDto,
    ValidateRedirectTargetRequest,
    ValidateRedirectTargetResponse,
)

logger = logging.getLogger(__name__)


class SsoRedirectService:
    """Service providing open-redirect defense, idempotent URL rewriting, and probe hysteresis."""

    def __init__(
        self,
        sanitizer: SsoUrlSanitizer | None = None,
        hysteresis_controller: ProbeHysteresisController | None = None,
    ) -> None:
        self._sanitizer = sanitizer or SsoUrlSanitizer()
        self._hysteresis = hysteresis_controller or ProbeHysteresisController()

    def validate_target(
        self, request: ValidateRedirectTargetRequest
    ) -> ValidateRedirectTargetResponse:
        """Validate target redirect URL safety against open redirects."""
        whitelist = (
            frozenset(h.lower() for h in request.allowed_absolute_hosts)
            if request.allowed_absolute_hosts
            else None
        )
        res: SsoRedirectValidation = self._sanitizer.validate_redirect_target(
            target_url=request.target_url,
            allowed_absolute_hosts=whitelist,
        )

        return ValidateRedirectTargetResponse(
            target_url=res.target_url,
            is_safe=res.is_safe,
            category=UrlPathCategoryDto(res.category.value),
            reason=res.reason,
        )

    def build_redirect_url(
        self, request: BuildSsoRedirectUrlRequest
    ) -> BuildSsoRedirectUrlResponse:
        """Strip existing authorization codes and append new code idempotently."""
        res: SsoRedirectBuildResult = self._sanitizer.build_sso_redirect_url(
            redirect_uri=request.redirect_uri,
            sso_code=request.sso_code,
            code_param=request.code_param,
        )

        return BuildSsoRedirectUrlResponse(
            original_url=res.original_url,
            cleaned_url=res.cleaned_url,
            final_url=res.final_url,
            code_attached=res.code_attached,
            is_relative=res.is_relative,
        )

    def evaluate_probe(self, request: EvaluateProbeRequest) -> EvaluateProbeResponse:
        """Record probe outcome and determine hysteresis state transition."""
        res: ProbeEvaluationResult = self._hysteresis.record_probe_result(
            is_success=request.is_success
        )

        return EvaluateProbeResponse(
            previous_state=res.previous_state.value,
            new_state=res.new_state.value,
            consecutive_failures=res.consecutive_failures,
            consecutive_successes=res.consecutive_successes,
            state_changed=res.state_changed,
            recommended_action=res.recommended_action,
        )
