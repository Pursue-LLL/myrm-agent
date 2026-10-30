"""Mascot services package.

Provides the event-to-mascot-status mapping used for mascot animation states.
"""

from .status_mapper import MascotStateMapper, MascotStatus

__all__ = [
    "MascotStatus",
    "MascotStateMapper",
]
