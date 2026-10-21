"""Shared HTTP timeout resolution for channel API clients.

Safety-clamps timeout values to [1.0, 300.0] range.

[INPUT]
- (none)

[OUTPUT]
- resolve_timeout: Resolve HTTP timeout with optional override and safety clamp.

[POS]
app.channels.providers._http_timeout — Shared HTTP timeout resolution for channel API clients.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.coercion import parse_float

logger = logging.getLogger(__name__)

_MIN_TIMEOUT: float = 1.0
_MAX_TIMEOUT: float = 300.0


def resolve_timeout(default: float, override: float | None = None) -> float:
    """Resolve HTTP timeout with optional override and safety clamp.

    Args:
        default: Default timeout in seconds.
        override: Optional explicit override value.

    Returns:
        Clamped timeout value in seconds.
    """
    value = override if override is not None else default
    clamped = parse_float(value, _MIN_TIMEOUT, min_val=_MIN_TIMEOUT, max_val=_MAX_TIMEOUT)
    if clamped != value:
        logger.warning(
            "Timeout %.1f clamped to %.1f (bounds: [%.0f, %.0f])",
            value,
            clamped,
            _MIN_TIMEOUT,
            _MAX_TIMEOUT,
        )
    return clamped
