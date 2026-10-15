"""Mascot services package.

Provides status mapping, emotional transitions, and cache cleanup for Mascot systems.
"""

from .status_mapper import MascotStateMapper, MascotStatus

__all__ = [
    "MascotStatus",
    "MascotStateMapper",
]
