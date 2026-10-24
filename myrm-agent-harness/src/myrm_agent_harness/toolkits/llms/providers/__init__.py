"""Custom LiteLLM providers (lazy registration).

[INPUT]
- .minimax_image (POS: MiniMax image-01 custom provider)
- .yunshu (POS: Yunshu custom provider)

[OUTPUT]
- ensure_providers_registered: import the provider modules once so they append
  themselves to ``litellm.custom_provider_map``

[POS]
Provider package facade. The provider modules import litellm (the single heaviest
startup dependency), so registration happens on first model creation instead of at
package import time.
"""

from __future__ import annotations

import threading

_registration_lock = threading.Lock()
_registered = False


def ensure_providers_registered() -> None:
    """Register every custom provider once; safe to call from concurrent threads."""
    global _registered
    if _registered:
        return
    with _registration_lock:
        if _registered:
            return
        from . import minimax_image, yunshu  # noqa: F401  (import registers both providers)

        _registered = True
