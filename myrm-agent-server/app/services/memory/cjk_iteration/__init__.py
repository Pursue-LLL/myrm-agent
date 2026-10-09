"""CJK iteration mark disambiguation and recall matching service module.

[POS]
Exports service provider and singleton accessor for CJK iteration mark resolution.

[INPUT]
- app.services.memory.cjk_iteration.provider

[OUTPUT]
- CjkIterationServiceProvider
- get_cjk_iteration_service_provider
"""

from __future__ import annotations

from app.services.memory.cjk_iteration.provider import (
    CjkIterationServiceProvider,
    get_cjk_iteration_service_provider,
)

__all__ = [
    "CjkIterationServiceProvider",
    "get_cjk_iteration_service_provider",
]
