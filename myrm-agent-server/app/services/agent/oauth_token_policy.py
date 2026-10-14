"""Pure OAuth token-lifetime and refresh-failure policy.

[INPUT]
- stdlib only (base64, hashlib, json, math)

[OUTPUT]
- TOKEN_REFRESH_LEAD_S / DEFAULT_TOKEN_TTL_S: shared freshness constants
- jwt_expiry / resolve_expires_at: expiry of a freshly issued access token
- credential_expiry / is_refresh_due: expiry of a stored credential entry
- is_renewable: whether a stored credential can renew its own access token
- classify_refresh_failure / RefreshFailureKind: retry-heals vs needs re-authorization
- refresh_token_fingerprint: non-reversible identity of a refresh token

[POS]
Shared by the OAuth refresher, the xAI device-code login and the LLM token custody
module so they agree on when an access token is stale and which refresh failures can
heal by retrying. No I/O, no module state.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Literal

# Refresh this long before the access token actually expires so a request that
# starts just before expiry still carries a valid token to the provider.
TOKEN_REFRESH_LEAD_S = 300

# Assumed lifetime when neither the token response nor the token itself states one.
DEFAULT_TOKEN_TTL_S = 3600

RefreshFailureKind = Literal["terminal", "transient"]

# RFC 6749 section 5.2 answers a rejected grant or client with 400 (401 when client
# authentication failed). Every other status comes from something in front of the
# grant: a gateway, a rate limit, or an access gate such as xAI's 403 for a plan that
# may not use the API, which signing in again does not lift.
_REJECTION_STATUS_CODES = frozenset({400, 401})
_TRANSIENT_ERROR_CODES = frozenset({"temporarily_unavailable", "server_error", "slow_down"})


def _positive_number(value: object) -> float | None:
    """Coerce a JSON/string number to a finite positive float, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def jwt_expiry(token: object) -> float | None:
    """Return the ``exp`` claim (epoch seconds) of a JWT access token.

    The signature is deliberately not verified: the claim only schedules our
    own refresh, the resource server remains the authority on validity.
    Opaque (non-JWT) tokens yield None.
    """
    if not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    segment = parts[1]
    try:
        payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    except ValueError:
        return None
    return _positive_number(payload.get("exp")) if isinstance(payload, dict) else None


def resolve_expires_at(token: object, expires_in: object, *, now: float) -> float:
    """Epoch-seconds expiry of a freshly issued access token.

    The earlier of the token's own ``exp`` and ``now + expires_in`` wins, so a
    provider that reports a generous ``expires_in`` (or none) cannot make a
    short-lived JWT look fresh for hours.
    """
    candidates: list[float] = []
    exp = jwt_expiry(token)
    if exp is not None:
        candidates.append(exp)
    ttl = _positive_number(expires_in)
    if ttl is not None:
        candidates.append(now + ttl)
    return min(candidates) if candidates else now + DEFAULT_TOKEN_TTL_S


def credential_expiry(credential: Mapping[str, object]) -> float | None:
    """Effective expiry of a stored credential entry (None when unknown).

    A stored ``expires_at`` may lie beyond the token's real lifetime; the earlier
    of it and the JWT ``exp`` wins, so such an entry never looks fresh.
    """
    candidates = [
        value
        for value in (_positive_number(credential.get("expires_at")), jwt_expiry(credential.get("token")))
        if value is not None
    ]
    return min(candidates) if candidates else None


def is_refresh_due(credential: Mapping[str, object], *, now: float) -> bool:
    """True when the stored access token expires within the refresh lead window.

    An unknown expiry is not "due": callers that already know the token was
    rejected refresh unconditionally instead of consulting this predicate.
    """
    expiry = credential_expiry(credential)
    return expiry is not None and expiry <= now + TOKEN_REFRESH_LEAD_S


def is_renewable(credential: Mapping[str, object]) -> bool:
    """True when a stored credential carries what a refresh needs.

    Such a credential keeps working past its access-token expiry, so that expiry
    says nothing about whether the connection is usable.
    """
    return bool(credential.get("refresh_token")) and bool(credential.get("token_url"))


def classify_refresh_failure(status_code: int, body: object) -> RefreshFailureKind:
    """Decide whether a failed refresh can heal by retrying later.

    ``terminal`` means the provider itself rejected this refresh token or client:
    status 400 or 401 with an OAuth error body (RFC 6749 section 5.2, JSON
    carrying ``error``). Retrying only spends (and, for rotating tokens, burns)
    attempts until the user signs in again. ``transient`` covers every other
    outcome: outages, rate limits, redirects, 400/401 answers without an OAuth
    error body (a proxy, gateway or firewall in front of the provider) and access
    gates such as 403, none of which signing in again would change.
    """
    if status_code not in _REJECTION_STATUS_CODES:
        return "transient"
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, str) or not error or error in _TRANSIENT_ERROR_CODES:
        return "transient"
    return "terminal"


def refresh_token_fingerprint(refresh_token: str) -> str:
    """Short non-reversible identity used to remember a rejected refresh token."""
    return hashlib.sha256(refresh_token.encode()).hexdigest()[:16]
