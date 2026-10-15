"""A mutating route may skip the auth middleware only when its handler authenticates the caller itself.

[POS]
tests/architecture/test_public_mutating_routes.py

[INPUT]
- tests.support.public_api_app: full OpenAPI path + method table
- app.core.security.auth.public_paths::is_public_path: the admission rule the middlewares apply

[OUTPUT]
- Fails when a mutating route is public without an entry below (a path-prefix whitelist silently covered it)
- Fails when an entry goes stale (route gone, or it is no longer public) so the registry can only list live exceptions

Public prefixes exist so probes, discovery and login work without credentials, but a prefix also swallows every
operator action mounted beneath it. Each entry names the handler-level check that replaces the middleware for it.
"""

from __future__ import annotations

from app.core.security.auth.public_paths import is_public_path
from tests.support.public_api_app import public_api_openapi

_MUTATING_VERBS = frozenset({"post", "put", "delete", "patch"})

Operation = tuple[str, str]

_SELF_AUTHENTICATED: dict[Operation, str] = {
    ("POST", "/api/v1/a2a/rpc"): (
        "peer bearer token resolved in-handler; callers it does not trust only queue tasks that need operator approval "
        "(app/api/a2a/router.py `_dispatch_rpc`)"
    ),
    ("POST", "/api/v1/a2a/agents/{agent_id}/rpc"): "same dispatcher as the root endpoint (app/api/a2a/router.py)",
    ("POST", "/api/v1/public/artifact-share/{token}"): (
        "read-only serving: the HMAC-signed token in the path and an optional body password gate access "
        "(app/api/files/artifact_share_public.py `_auth_or_gate`)"
    ),
    ("POST", "/api/v1/public/artifact-share/{token}/"): "same gate as the bare token route",
    ("POST", "/api/v1/public/artifact-share/{token}/{asset_path}"): "same gate as the bare token route",
    ("POST", "/webui/auth/login"): "username and password in the body, failed attempts rate limited (WebuiAuthService.login)",
    ("POST", "/webui/auth/setup"): "one-time setup token, refused once an admin exists (WebuiAuthService.setup_admin)",
    ("POST", "/webui/auth/token-exchange"): "short-lived temp token (WebuiAuthService.exchange_temp_token)",
    ("POST", "/webui/auth/logout"): "only clears the caller's own session cookie",
    ("POST", "/webui/auth/change-password"): "current password verified (WebuiAuthService.change_password)",
    ("POST", "/webui/auth/disable-protection"): "admin password verified (WebuiAuthService.disable_password_protection)",
    ("POST", "/webui/auth/generate-setup-token"): (
        "loopback before an admin exists, an authenticated session afterwards (WebuiAuthService.generate_setup_token)"
    ),
    ("PUT", "/webui/auth/protection"): (
        "requires an authenticated session or trusted loopback (app/api/webui/auth_routes.py `update_protection_config`)"
    ),
}


def _public_mutating_operations() -> set[Operation]:
    return {
        (verb.upper(), path)
        for path, operations in public_api_openapi().paths.items()
        for verb in operations
        if verb in _MUTATING_VERBS and is_public_path(path, verb)
    }


def test_public_mutating_routes_are_registered_as_self_authenticated() -> None:
    unregistered = sorted(_public_mutating_operations() - _SELF_AUTHENTICATED.keys())
    assert not unregistered, (
        "These mutating routes skip the auth middleware without a handler-level check on record. Narrow the matching "
        "rule in app/core/security/auth/public_paths.py, or authenticate the caller in the handler and register it here: "
        f"{unregistered}"
    )


def test_registered_public_mutating_routes_are_still_public() -> None:
    stale = sorted(_SELF_AUTHENTICATED.keys() - _public_mutating_operations())
    assert not stale, f"Registry entries whose route is gone or no longer public; delete them: {stale}"
