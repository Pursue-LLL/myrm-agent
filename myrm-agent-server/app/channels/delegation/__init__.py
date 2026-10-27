"""Delegation coordination and in-flight steering subsystem.

[INPUT]
- .delegation_coordinator::DelegationCoordinator
- .delegation_delivery::build_delivery_message
- .delegation_ingress::DelegationIngressGuard, build_delegation_task
- .delegation_models::DelegationStatus, DelegationTask

[OUTPUT]
- Public exports for delegation subsystem

[POS]
Subsystem public API and data models for channel task delegation and delivery.
"""

from .delegation_coordinator import DelegationCoordinator
from .delegation_delivery import build_delivery_message
from .delegation_ingress import (
    DelegationIngressGuard,
    build_delegation_task,
    is_delegation_intent,
)
from .delegation_models import DelegationStatus, DelegationTask

__all__ = [
    "DelegationCoordinator",
    "DelegationIngressGuard",
    "DelegationStatus",
    "DelegationTask",
    "build_delegation_task",
    "build_delivery_message",
    "is_delegation_intent",
]
