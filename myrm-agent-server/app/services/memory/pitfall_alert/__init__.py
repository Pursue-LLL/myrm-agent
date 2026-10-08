"""Pitfall alert package.

[POS]
Exports the pitfall alert service provider and its accessor.

[INPUT]
- .provider.PitfallAlertServiceProvider, get_pitfall_alert_service

[OUTPUT]
- PitfallAlertServiceProvider, get_pitfall_alert_service
"""

from __future__ import annotations

from app.services.memory.pitfall_alert.provider import (
    PitfallAlertServiceProvider,
    get_pitfall_alert_service,
)

__all__ = [
    "PitfallAlertServiceProvider",
    "get_pitfall_alert_service",
]
