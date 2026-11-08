"""Retry policy of one provider request: which failures are worth another attempt and how long to wait.

[INPUT]
- httpx (POS: the failed answer's status and headers, or the transport error)

[OUTPUT]
- DEFAULT_RETRIES: retries a model call is allowed after its first attempt
- answer_wait / error_wait: seconds to wait before the next attempt, ``None`` when the failure is final

[POS]
A failure before the model has produced anything carries no partial output, so retrying it cannot duplicate or reorder
what the caller has seen: a refused or dropped connection and a 408/409/429/5xx answer. Two retries at 0.5 s doubling
to 8 s with jitter, the provider's own Retry-After honoured while it fits that ceiling, absorb the blips of a healthy
provider. Anything that takes longer belongs to the agent layer above, which sees what survives this one: a provider
silent for the whole request limit is not asked again and a longer Retry-After is passed up at once, so that layer can
rotate keys, fail over or wait in view of the user instead of the call blocking unseen.
"""

from __future__ import annotations

import email.utils
import random
import time
from typing import Final

import httpx

DEFAULT_RETRIES: Final = 2

_RETRYABLE_STATUSES: Final = frozenset({408, 409, 429})
# Failures that come back at once and say nothing about the request. ReadTimeout and WriteTimeout are left out on purpose:
# they are the provider's silence for the whole request limit.
_TRANSIENT_ERRORS: Final = (httpx.ConnectTimeout, httpx.PoolTimeout, httpx.NetworkError, httpx.RemoteProtocolError)
# The request never reached the provider, so a second try is safe even for a call that must not be repeated.
_NEVER_SENT: Final = (httpx.ConnectError, httpx.ConnectTimeout)
_INITIAL_DELAY: Final = 0.5
_MAX_DELAY: Final = 8.0
# A longer boundary is a quota window or an outage: waiting it out inside the call would hide it from key rotation,
# failover and the user. The backoff ceiling is the longest the call blocks for one retry.
_MAX_RETRY_AFTER: Final = _MAX_DELAY


def _backoff(retry: int) -> float:
    """Delay before retry number ``retry`` (1-based); the jitter keeps many clients from retrying in step."""
    return min(_INITIAL_DELAY * 2.0 ** (retry - 1), _MAX_DELAY) * (1.0 - 0.25 * random.random())


def _stated_delay(headers: httpx.Headers) -> float | None:
    """The provider's own boundary: ``retry-after-ms``, or ``retry-after`` as seconds or as an HTTP date."""
    milliseconds = headers.get("retry-after-ms")
    if milliseconds is not None:
        try:
            return float(milliseconds) / 1000
        except ValueError:
            pass
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    parsed = email.utils.parsedate_tz(raw)
    return None if parsed is None else email.utils.mktime_tz(parsed) - time.time()


def answer_wait(response: httpx.Response, retries_done: int, retries: int) -> float | None:
    """Seconds to wait before retrying a failed answer; ``None`` when the answer is final."""
    if response.is_success or retries_done >= retries:
        return None
    advice = response.headers.get("x-should-retry")  # the provider can overrule the status-based default
    status = response.status_code
    if advice == "false" or (advice != "true" and status not in _RETRYABLE_STATUSES and status < 500):
        return None
    stated = _stated_delay(response.headers)
    if stated is None or stated <= 0:
        return _backoff(retries_done + 1)
    return stated if stated <= _MAX_RETRY_AFTER else None


def error_wait(error: httpx.TransportError, retries_done: int, retries: int) -> float | None:
    """Seconds to wait before retrying after a transport error; ``None`` when it is final."""
    if not isinstance(error, _TRANSIENT_ERRORS):
        return None
    allowed = max(retries, 1) if isinstance(error, _NEVER_SENT) else retries
    return _backoff(retries_done + 1) if retries_done < allowed else None
