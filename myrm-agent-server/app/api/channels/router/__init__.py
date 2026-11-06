"""Channel management API.

[INPUT]
- .channels / .pairings / .groups (POS: endpoint modules)

[OUTPUT]
- router

[POS]
Aggregate exit of the channel router package.
"""

from __future__ import annotations

from . import channels, groups, pairings  # noqa: F401  (register routes)
from .common import _CHANNEL_CONFIG_KEYS, channel_credentials_key, router

__all__ = ["router", "_CHANNEL_CONFIG_KEYS", "channel_credentials_key"]
