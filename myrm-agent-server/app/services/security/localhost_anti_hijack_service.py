"""Service for localhost anti-DNS-rebinding and origin anti-hijack defense.

[INPUT]
Harness core localhost anti-hijack middleware, schemas, and runtime settings.

[OUTPUT]
LocalhostAntiHijackService, get_localhost_anti_hijack_service.

[POS]
Service layer providing DNS rebinding status, origin allowlist management, and security audit records.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.localhost_anti_hijack import (
    HostOriginGuard,
    HostOriginPolicy,
    SessionCookieSpec,
    SetupTokenManager,
    SetupTokenRecord,
    ValidationResult,
)


class LocalhostAntiHijackService:
    """Coordinates local token exchange and origin validation guards."""

    def __init__(
        self,
        policy: HostOriginPolicy | None = None,
        cookie_name: str = "myrm_local_session",
        cookie_max_age: int = 86400,
        cookie_secure: bool = False,
    ) -> None:
        self._token_manager = SetupTokenManager(
            cookie_name=cookie_name,
            cookie_max_age=cookie_max_age,
            cookie_secure=cookie_secure,
        )
        self._origin_guard = HostOriginGuard(policy=policy)

    @property
    def token_manager(self) -> SetupTokenManager:
        """Access the underlying SetupTokenManager instance."""
        return self._token_manager

    @property
    def origin_guard(self) -> HostOriginGuard:
        """Access the underlying HostOriginGuard instance."""
        return self._origin_guard

    def generate_setup_token(
        self,
        ttl_seconds: int = 300,
        client_binding: str | None = None,
    ) -> SetupTokenRecord:
        """Generate a one-time startup setup token."""
        return self._token_manager.generate_token(
            ttl_seconds=ttl_seconds,
            client_binding=client_binding,
        )

    def exchange_token(
        self,
        token: str,
        client_binding: str | None = None,
    ) -> tuple[bool, str, SessionCookieSpec | None]:
        """Exchange the setup token for an HttpOnly session cookie spec."""
        return self._token_manager.consume_token(
            token=token,
            client_binding=client_binding,
        )

    def verify_request(
        self,
        host: str | None,
        origin: str | None,
        referer: str | None = None,
        client_ip: str | None = None,
    ) -> ValidationResult:
        """Verify host, origin, and referer headers against anti-hijack policy."""
        return self._origin_guard.verify_request(
            host=host,
            origin=origin,
            referer=referer,
            client_ip=client_ip,
        )

    def validate_session(self, session_id: str) -> bool:
        """Check if an active session ID is valid and unexpired."""
        return self._token_manager.validate_session(session_id)

    def revoke_session(self, session_id: str) -> bool:
        """Revoke a session ID."""
        return self._token_manager.revoke_session(session_id)

    def get_policy(self) -> HostOriginPolicy:
        """Return the current HostOriginPolicy."""
        return self._origin_guard.policy


_singleton_service: LocalhostAntiHijackService | None = None


def get_localhost_anti_hijack_service() -> LocalhostAntiHijackService:
    """Retrieve or initialize the singleton LocalhostAntiHijackService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = LocalhostAntiHijackService()
    return _singleton_service
