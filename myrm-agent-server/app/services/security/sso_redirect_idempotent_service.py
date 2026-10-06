"""Service layer for SSO Redirect Idempotence and Probe Hysteresis.

[INPUT]
SSO redirect requests, probe events, and navigation target URLs from client or API endpoints.

[OUTPUT]
Sanitized redirect URLs, probe evaluation results, and anti-flapping hysteresis state.

[POS]
Service layer protecting against open redirect vulnerabilities and eliminating SSO parameter inflation.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.sso_redirect_idempotent import (
    ProbeEvaluation,
    ProbeHysteresisConfig,
    ProbeHysteresisTracker,
    SafeNavigationOptions,
    SsoRedirectResult,
    build_sso_redirect_url,
    is_safe_navigation_target,
    is_same_origin_relative_path,
    resolve_safe_redirect_target,
)

from app.schemas.sso_redirect_idempotent import (
    BuildSsoRedirectRequest,
    BuildSsoRedirectResponse,
    RecordProbeRequest,
    RecordProbeResponse,
    ValidateNavigationTargetRequest,
    ValidateNavigationTargetResponse,
)

logger = logging.getLogger(__name__)


class SsoRedirectIdempotentService:
    """Service orchestrating idempotent SSO redirects and probe hysteresis tracking."""

    def __init__(
        self,
        tracker: ProbeHysteresisTracker | None = None,
        hysteresis_config: ProbeHysteresisConfig | None = None,
    ) -> None:
        self._tracker = tracker or ProbeHysteresisTracker(config=hysteresis_config)

    def build_redirect_url(
        self, req: BuildSsoRedirectRequest
    ) -> BuildSsoRedirectResponse:
        """Construct an idempotent SSO redirect URL with stale codes stripped."""
        opts = SafeNavigationOptions(
            allow_deep_link=req.allow_deep_link,
            allowed_origins=tuple(req.allowed_origins)
            if req.allowed_origins is not None
            else None,
            fallback_url=req.fallback_url,
        )
        res: SsoRedirectResult = build_sso_redirect_url(
            redirect_uri=req.redirect_uri,
            sso_code=req.sso_code,
            param_name=req.param_name,
            options=opts,
        )

        if res.stripped_existing_code:
            logger.info(
                "Stripped stale '%s' parameter from redirect URI to prevent recursive ballooning",
                req.param_name,
            )

        if not res.is_safe_target:
            logger.warning(
                "SSO redirect URI '%s' failed safety validation; will resolve to fallback",
                req.redirect_uri,
            )

        return BuildSsoRedirectResponse(
            original_uri=res.original_uri,
            redirect_url=res.redirect_url,
            stripped_existing_code=res.stripped_existing_code,
            is_relative=res.is_relative,
            is_safe_target=res.is_safe_target,
        )

    def validate_navigation_target(
        self, req: ValidateNavigationTargetRequest
    ) -> ValidateNavigationTargetResponse:
        """Validate destination safety against open redirect attacks."""
        opts = SafeNavigationOptions(
            allow_deep_link=req.allow_deep_link,
            allowed_origins=tuple(req.allowed_origins)
            if req.allowed_origins is not None
            else None,
            fallback_url=req.fallback_url,
        )
        is_safe = is_safe_navigation_target(req.target, opts)
        is_rel = is_same_origin_relative_path(req.target)
        resolved = resolve_safe_redirect_target(req.target, opts)

        return ValidateNavigationTargetResponse(
            target=req.target,
            is_safe=is_safe,
            is_same_origin_relative=is_rel,
            resolved_safe_target=resolved,
        )

    def record_probe(self, req: RecordProbeRequest) -> RecordProbeResponse:
        """Record network health probe and update hysteresis dampening state."""
        eval_result: ProbeEvaluation = self._tracker.record_probe(
            healthy=req.healthy,
            current_url=req.current_url,
        )

        if eval_result.transitioned_to_offline:
            logger.warning(
                "Probe hysteresis threshold reached (%d consecutive fails); switching client to offline mode",
                eval_result.consecutive_fails,
            )
        elif eval_result.transitioned_to_online:
            logger.info(
                "Network probe recovered; restoring client to active location: %s",
                eval_result.suggested_navigation_url,
            )

        return RecordProbeResponse(
            is_online=eval_result.is_online,
            transitioned_to_offline=eval_result.transitioned_to_offline,
            transitioned_to_online=eval_result.transitioned_to_online,
            consecutive_fails=eval_result.consecutive_fails,
            last_healthy_url=eval_result.last_healthy_url,
            suggested_navigation_url=eval_result.suggested_navigation_url,
        )


sso_redirect_idempotent_service = SsoRedirectIdempotentService()


def get_sso_redirect_idempotent_service() -> SsoRedirectIdempotentService:
    """Provide singleton instance of SsoRedirectIdempotentService."""
    return sso_redirect_idempotent_service
