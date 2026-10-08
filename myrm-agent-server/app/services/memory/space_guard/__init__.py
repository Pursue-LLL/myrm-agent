"""Vector space guard service package.

[POS]
Business service package managing embedding model space integrity and validation.

[INPUT]
- .provider (VectorSpaceGuardService, get_space_guard_service)

[OUTPUT]
- VectorSpaceGuardService, get_space_guard_service
"""

from app.services.memory.space_guard.provider import (
    VectorSpaceGuardService,
    get_space_guard_service,
)

__all__ = [
    "VectorSpaceGuardService",
    "get_space_guard_service",
]
