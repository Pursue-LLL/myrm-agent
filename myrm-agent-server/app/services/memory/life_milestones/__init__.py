"""Life milestones package.

[POS]
Exports the life milestones suite singleton accessors.

[INPUT]
- .provider.get_life_milestones_suite, reset_life_milestones_suite

[OUTPUT]
- get_life_milestones_suite, reset_life_milestones_suite
"""

from __future__ import annotations

from app.services.memory.life_milestones.provider import (
    get_life_milestones_suite,
    reset_life_milestones_suite,
)

__all__ = [
    "get_life_milestones_suite",
    "reset_life_milestones_suite",
]
