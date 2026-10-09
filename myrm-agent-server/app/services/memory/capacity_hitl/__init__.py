"""[POS]: app/services/memory/capacity_hitl/__init__.py
[INPUT]: None.
[OUTPUT]: Public exports for CapacityHitlProvider singleton and dependency injection helper.
"""

from app.services.memory.capacity_hitl.provider import (
    CapacityHitlProvider,
    get_capacity_hitl_service,
)

__all__ = [
    "CapacityHitlProvider",
    "get_capacity_hitl_service",
]
