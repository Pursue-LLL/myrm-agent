"""[INPUT] MachineNode, MachineMetrics, and Takeover schemas and service.
[OUTPUT] Public exports for self-hosted machine service.
[POS] app/services/machines/__init__.py.
"""

from .machine_service import MachineService
from .machine_types import (
    MachineMetrics,
    MachineNode,
    MachinePlatform,
    MachineStatus,
    RegistrationTokenResponse,
    TakeoverActionRequest,
    TakeoverSession,
    TakeoverState,
)

__all__ = [
    "MachineMetrics",
    "MachineNode",
    "MachinePlatform",
    "MachineService",
    "MachineStatus",
    "RegistrationTokenResponse",
    "TakeoverActionRequest",
    "TakeoverSession",
    "TakeoverState",
]
