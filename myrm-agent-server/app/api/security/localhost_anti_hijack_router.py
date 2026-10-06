"""API endpoints for localhost anti-DNS-rebinding and origin anti-hijack guard.

[INPUT]
FastAPI APIRouter, response dependencies, localhost anti-hijack service and schemas.

[OUTPUT]
router: API endpoints for localhost security status, origin audit records, and security config updates.

[POS]
Router for runtime localhost anti-DNS-rebinding policy queries and host header protection audits.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.schemas.localhost_anti_hijack import (
    AntiHijackPolicyResponse,
    GenerateSetupTokenResponse,
    HostOriginVerifyRequest,
    HostOriginVerifyResponse,
    RevokeSessionRequest,
    RevokeSessionResponse,
    SetupTokenExchangeRequest,
    SetupTokenExchangeResponse,
)
from app.services.security.localhost_anti_hijack_service import (
    LocalhostAntiHijackService,
    get_localhost_anti_hijack_service,
)

router = APIRouter(prefix="/anti-hijack", tags=["Localhost Anti-Hijack Guard"])


@router.post(
    "/generate-token",
    response_model=GenerateSetupTokenResponse,
    summary="Generate one-time setup token for local WebUI startup",
)
def generate_setup_token(
    ttl_seconds: int = 300,
    client_binding: str | None = None,
    service: LocalhostAntiHijackService = Depends(
        get_localhost_anti_hijack_service
    ),
) -> GenerateSetupTokenResponse:
    """Generate high-entropy startup token for URL query handoff to browser."""
    record = service.generate_setup_token(
        ttl_seconds=ttl_seconds, client_binding=client_binding
    )
    return GenerateSetupTokenResponse(
        token=record.token,
        expires_at=record.expires_at,
        ttl_seconds=ttl_seconds,
    )


@router.post(
    "/exchange-token",
    response_model=SetupTokenExchangeResponse,
    summary="Exchange setup token for HttpOnly session cookie",
)
def exchange_setup_token(
    payload: SetupTokenExchangeRequest,
    response: Response,
    service: LocalhostAntiHijackService = Depends(
        get_localhost_anti_hijack_service
    ),
) -> SetupTokenExchangeResponse:
    """Verify single-use token and issue strict HttpOnly session cookie."""
    success, message, cookie_spec = service.exchange_token(
        token=payload.token,
        client_binding=payload.client_identifier,
    )
    if not success or cookie_spec is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Set strict HttpOnly session cookie
    response.set_cookie(
        key=cookie_spec.cookie_name,
        value=cookie_spec.session_id,
        max_age=cookie_spec.max_age,
        httponly=cookie_spec.httponly,
        samesite=cookie_spec.samesite,
        secure=cookie_spec.secure,
        path=cookie_spec.path,
    )

    return SetupTokenExchangeResponse(
        success=True,
        session_id=cookie_spec.session_id,
        message=message,
        cookie_name=cookie_spec.cookie_name,
    )


@router.post(
    "/verify-request",
    response_model=HostOriginVerifyResponse,
    summary="Verify Host and Origin headers against DNS rebinding policy",
)
def verify_request_headers(
    payload: HostOriginVerifyRequest,
    service: LocalhostAntiHijackService = Depends(
        get_localhost_anti_hijack_service
    ),
) -> HostOriginVerifyResponse:
    """Inspect Host, Origin, and Referer headers to block cross-site abuse."""
    result = service.verify_request(
        host=payload.host,
        origin=payload.origin,
        referer=payload.referer,
        client_ip=payload.client_ip,
    )
    return HostOriginVerifyResponse(
        is_allowed=result.is_allowed,
        status=result.status,
        reason=result.reason,
        host_header=result.host_header,
        origin_header=result.origin_header,
    )


@router.get(
    "/policy",
    response_model=AntiHijackPolicyResponse,
    summary="Get current allowed hosts and origins policy",
)
def get_anti_hijack_policy(
    service: LocalhostAntiHijackService = Depends(
        get_localhost_anti_hijack_service
    ),
) -> AntiHijackPolicyResponse:
    """Return active allowed hosts and origins whitelist configuration."""
    policy = service.get_policy()
    return AntiHijackPolicyResponse(
        allowed_hosts=list(policy.allowed_hosts),
        allowed_origins=list(policy.allowed_origins),
        allow_null_origin=policy.allow_null_origin,
        enforce_strict_mode=policy.enforce_strict_mode,
    )


@router.post(
    "/revoke-session",
    response_model=RevokeSessionResponse,
    summary="Revoke active session and delete session cookie",
)
def revoke_session(
    payload: RevokeSessionRequest,
    response: Response,
    service: LocalhostAntiHijackService = Depends(
        get_localhost_anti_hijack_service
    ),
) -> RevokeSessionResponse:
    """Invalidate active session and wipe out the client session cookie."""
    success = service.revoke_session(payload.session_id)
    policy = service.get_policy()
    _ = policy  # Keep reference for consistency
    response.delete_cookie(key="myrm_local_session", path="/")
    if not success:
        return RevokeSessionResponse(
            success=False,
            message="Session not found or already expired",
        )
    return RevokeSessionResponse(
        success=True,
        message="Session revoked and cookie cleared",
    )
