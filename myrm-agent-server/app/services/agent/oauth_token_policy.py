"""Pure OAuth token-lifetime and refresh-failure policy.

[INPUT]
- stdlib only (base64, hashlib, json, math)

[OUTPUT]
- TOKEN_REFRESH_LEAD_S / DEFAULT_TOKEN_TTL_S: shared freshness constants
- jwt_expiry / resolve_expires_at: expiry of a freshly issued access token
- credential_expiry / is_refresh_due: expiry of a stored credential entry
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

# Request timeouts and rate limits heal on retry whatever the body says; for any
# other 4xx only an OAuth error body proves the provider rejected the grant.
_TRANSIENT_STATUS_CODES = frozenset({408, 425, 429})
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


def classify_refresh_failure(status_code: int, body: object) -> RefreshFailureKind:
    """Decide whether a failed refresh can heal by retrying later.

    ``terminal`` means the provider itself rejected this refresh token or client:
    a client-error status with an OAuth error body (RFC 6749 section 5.2, JSON
    carrying ``error``). Retrying only spends (and, for rotating tokens, burns)
    attempts until the user signs in again. ``transient`` covers outages, rate
    limits, unknown non-error statuses and 4xx answers without an OAuth error
    body: those come from a proxy, gateway or firewall in front of the provider
    and heal on their own.
    """
    if status_code < 400 or status_code >= 500 or status_code in _TRANSIENT_STATUS_CODES:
        return "transient"
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, str) or not error or error in _TRANSIENT_ERROR_CODES:
        return "transient"
    return "terminal"


def refresh_token_fingerprint(refresh_token: str) -> str:
    """Short non-reversible identity used to remember a rejected refresh token."""
    return hashlib.sha256(refresh_token.encode()).hexdigest()[:16]
