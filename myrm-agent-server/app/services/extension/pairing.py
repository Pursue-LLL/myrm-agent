"""One-time pairing tickets for browser extension onboarding.

[INPUT]
- secrets, time (POS: ticket generation and TTL)

[OUTPUT]
- create_pairing_ticket, consume_pairing_ticket, check_pairing_rate_limit

[POS]
In-memory one-shot pairing store for WebUI ↔ MV3 extension onboarding.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

_PAIRING_TTL_S = 300.0
_PAIRING_RATE_LIMIT_WINDOW_S = 60.0
_PAIRING_RATE_LIMIT_MAX = 20

_pairing_attempts: dict[str, list[float]] = {}


@dataclass(frozen=True, slots=True)
class PairingTicket:
    ws_url: str
    auth_token: str
    expires_at: float


_store: dict[str, PairingTicket] = {}


def create_pairing_ticket(*, ws_url: str, auth_token: str) -> tuple[str, float]:
    """Create a one-time pairing code."""
    _purge_expired()
    code = secrets.token_urlsafe(12)
    expires_at = time.monotonic() + _PAIRING_TTL_S
    _store[code] = PairingTicket(
        ws_url=ws_url,
        auth_token=auth_token,
        expires_at=expires_at,
    )
    return code, _PAIRING_TTL_S


def consume_pairing_ticket(code: str) -> PairingTicket | None:
    """Consume pairing code; returns None when invalid or expired."""
    _purge_expired()
    normalized = code.strip()
    if not normalized:
        return None
    ticket = _store.pop(normalized, None)
    if ticket is None or ticket.expires_at < time.monotonic():
        return None
    return ticket


def check_pairing_rate_limit(client_key: str) -> bool:
    """Return True when the client may consume a pairing ticket."""
    now = time.monotonic()
    window_start = now - _PAIRING_RATE_LIMIT_WINDOW_S
    attempts = [ts for ts in _pairing_attempts.get(client_key, []) if ts >= window_start]
    if len(attempts) >= _PAIRING_RATE_LIMIT_MAX:
        _pairing_attempts[client_key] = attempts
        return False
    attempts.append(now)
    _pairing_attempts[client_key] = attempts
    if len(_pairing_attempts) > 256:
        stale_keys = [key for key, values in _pairing_attempts.items() if not values or values[-1] < window_start]
        for key in stale_keys:
            del _pairing_attempts[key]
    return True


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [key for key, ticket in _store.items() if ticket.expires_at < now]
    for key in expired:
        del _store[key]
