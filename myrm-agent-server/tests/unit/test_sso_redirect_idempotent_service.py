"""Unit tests for SSO Redirect Idempotent and Probe Hysteresis Service.

Verifies service orchestration for idempotent redirect URLs, open redirect defense,
and probe hysteresis tracking.
"""

from app.schemas.sso_redirect_idempotent import (
    BuildSsoRedirectRequest,
    BuildSsoRedirectResponse,
    RecordProbeRequest,
    RecordProbeResponse,
    ValidateNavigationTargetRequest,
    ValidateNavigationTargetResponse,
)
from app.services.security.sso_redirect_idempotent_service import (
    SsoRedirectIdempotentService,
)


def test_build_redirect_url_basic_and_idempotent() -> None:
    service = SsoRedirectIdempotentService()

    # 1. Clean append
    req1 = BuildSsoRedirectRequest(
        redirect_uri="/admin/users?sort=asc",
        sso_code="code-fresh-01",
    )
    resp1: BuildSsoRedirectResponse = service.build_redirect_url(req1)
    assert resp1.redirect_url == "/admin/users?sort=asc&sso_code=code-fresh-01"
    assert resp1.stripped_existing_code is False
    assert resp1.is_relative is True
    assert resp1.is_safe_target is True

    # 2. Re-entrant redirect with stale sso_code: must strip old code!
    req2 = BuildSsoRedirectRequest(
        redirect_uri="/admin/users?sort=asc&sso_code=stale-old-code",
        sso_code="code-fresh-02",
    )
    resp2: BuildSsoRedirectResponse = service.build_redirect_url(req2)
    assert resp2.redirect_url == "/admin/users?sort=asc&sso_code=code-fresh-02"
    assert resp2.stripped_existing_code is True

    # 3. Open redirect target rejection
    req3 = BuildSsoRedirectRequest(
        redirect_uri="/\\evil.com",
        sso_code="code-03",
    )
    resp3: BuildSsoRedirectResponse = service.build_redirect_url(req3)
    assert resp3.is_safe_target is False


def test_validate_navigation_target() -> None:
    service = SsoRedirectIdempotentService()

    # Valid same-origin relative
    req_valid = ValidateNavigationTargetRequest(target="/edu/courses")
    resp_valid: ValidateNavigationTargetResponse = service.validate_navigation_target(
        req_valid
    )
    assert resp_valid.is_safe is True
    assert resp_valid.is_same_origin_relative is True
    assert resp_valid.resolved_safe_target == "/edu/courses"

    # WHATWG backslash exploit attempt
    req_exploit = ValidateNavigationTargetRequest(
        target="/\\evil.com",
        fallback_url="/home",
    )
    resp_exploit: ValidateNavigationTargetResponse = service.validate_navigation_target(
        req_exploit
    )
    assert resp_exploit.is_safe is False
    assert resp_exploit.is_same_origin_relative is False
    assert resp_exploit.resolved_safe_target == "/home"

    # Deep link permission check
    req_deep_denied = ValidateNavigationTargetRequest(
        target="myrm://sso/callback",
        allow_deep_link=False,
    )
    resp_deep_denied = service.validate_navigation_target(req_deep_denied)
    assert resp_deep_denied.is_safe is False

    req_deep_allowed = ValidateNavigationTargetRequest(
        target="myrm://sso/callback",
        allow_deep_link=True,
    )
    resp_deep_allowed = service.validate_navigation_target(req_deep_allowed)
    assert resp_deep_allowed.is_safe is True


def test_probe_hysteresis_recording() -> None:
    service = SsoRedirectIdempotentService()

    # Client viewing active task
    resp_healthy: RecordProbeResponse = service.record_probe(
        RecordProbeRequest(healthy=True, current_url="/tasks/active-run")
    )
    assert resp_healthy.is_online is True
    assert resp_healthy.consecutive_fails == 0
    assert resp_healthy.suggested_navigation_url == "/tasks/active-run"

    # First transient failure: dampened!
    resp_fail1 = service.record_probe(RecordProbeRequest(healthy=False))
    assert resp_fail1.is_online is True
    assert resp_fail1.transitioned_to_offline is False
    assert resp_fail1.consecutive_fails == 1
    assert resp_fail1.suggested_navigation_url == "/tasks/active-run"

    # Second failure: still dampened
    resp_fail2 = service.record_probe(RecordProbeRequest(healthy=False))
    assert resp_fail2.is_online is True
    assert resp_fail2.consecutive_fails == 2

    # Third failure: threshold reached, transitions to offline
    resp_fail3 = service.record_probe(RecordProbeRequest(healthy=False))
    assert resp_fail3.is_online is False
    assert resp_fail3.transitioned_to_offline is True
    assert resp_fail3.consecutive_fails == 3
    assert resp_fail3.suggested_navigation_url == "/offline"

    # Probe recovery: single healthy probe recovers back to online at original location
    resp_recovery = service.record_probe(RecordProbeRequest(healthy=True))
    assert resp_recovery.is_online is True
    assert resp_recovery.transitioned_to_online is True
    assert resp_recovery.consecutive_fails == 0
    assert resp_recovery.suggested_navigation_url == "/tasks/active-run"
