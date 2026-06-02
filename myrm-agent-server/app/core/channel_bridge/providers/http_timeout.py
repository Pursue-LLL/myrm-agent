"""Shared HTTP timeout resolution for channel API clients.

All channel API clients (`dingtalk/api`, `googlechat/api`, etc.) use this
module to resolve timeout values with environment variable override
and safety clamping.

Priority: environment variable > code default > clamp to [1.0, 300.0].
"""

from __future__ import annotations

import logging
import os

from myrm_agent_harness.utils.coercion import parse_float

logger = logging.getLogger(__name__)

_MIN_TIMEOUT: float = 1.0
_MAX_TIMEOUT: float = 300.0


def resolve_timeout(default: float, env_var: str | None = None) -> float:
    """Resolve HTTP timeout with optional env override and safety clamp.

    Args:
        default: Default timeout in seconds.
        env_var: Optional environment variable name for ops override.

    Returns:
        Clamped timeout value in seconds.
    """
    if env_var:
        raw = os.environ.get(env_var)
        if raw is not None:
            try:
                value = float(raw)
                clamped = parse_float(value, _MIN_TIMEOUT, min_val=_MIN_TIMEOUT, max_val=_MAX_TIMEOUT)
                if clamped != value:
                    logger.warning(
                        "Timeout %s=%s clamped to %.1f (bounds: [%.0f, %.0f])",
                        env_var,
                        raw,
                        clamped,
                        _MIN_TIMEOUT,
                        _MAX_TIMEOUT,
                    )
                return clamped
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid timeout %s=%s, using default %.1fs",
                    env_var,
                    raw,
                    default,
                )
    return parse_float(default, _MIN_TIMEOUT, min_val=_MIN_TIMEOUT, max_val=_MAX_TIMEOUT)
