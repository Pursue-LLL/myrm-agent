"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- CapabilityMixin

[POS]
Extension bridge mixin: capability normalisation and guards.
"""

from __future__ import annotations

from .common import (
    _ACTION_CAPABILITY_MAP,
    ExtensionBridgeNotAvailable,
)
from .state import BridgeState


class CapabilityMixin(BridgeState):
    @staticmethod
    def _normalize_capabilities(raw: object) -> set[str]:
        """Normalize extension capability payload to a lowercase token set."""
        if not isinstance(raw, list):
            return set()
        normalized: set[str] = set()
        for item in raw:
            if isinstance(item, str):
                cap = item.strip().lower()
                if cap:
                    normalized.add(cap)
        return normalized

    def _require_capability(self, capability: str) -> None:
        """Ensure extension handshake completed and capability is available."""
        if not self._hello_received:
            raise ExtensionBridgeNotAvailable("Extension handshake is not completed yet. Reconnect extension and retry.")
        if capability not in self._capabilities:
            raise ExtensionBridgeNotAvailable(
                f"Extension missing required capability '{capability}'. Please upgrade the browser extension and reconnect."
            )

    def _require_action_capability(self, action: str) -> None:
        """Enforce action-level capability contract for extension requests."""
        capability = _ACTION_CAPABILITY_MAP.get(action)
        if capability:
            self._require_capability(capability)
