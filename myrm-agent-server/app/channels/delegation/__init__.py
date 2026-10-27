"""Delegation coordination and in-flight steering subsystem.

[INPUT]
- .delegation_coordinator::DelegationCoordinator
- .delegation_delivery::build_delivery_card_content
- .delegation_ingress::DelegationIngressGuard, build_delegation_task
- .delegation_models::DelegationStatus, DelegationTask, DeliveryArtifact

[OUTPUT]
- Public exports for delegation subsystem

[POS]
Subsystem public API and data models for channel task delegation and delivery.
"""

from .delegation_coordinator import DelegationCoordinator
from .delegation_delivery import (
    build_delivery_card_content,
    format_file_size,
    scan_workspace_artifacts,
)
from .delegation_ingress import (
    DelegationIngressGuard,
    build_delegation_task,
    is_delegation_intent,
)
from .delegation_models import (
    DelegationStatus,
    DelegationTask,
    DeliveryArtifact,
)

__all__ = [
    "DelegationCoordinator",
    "DelegationIngressGuard",
    "DelegationStatus",
    "DelegationTask",
    "DeliveryArtifact",
    "build_delegation_task",
    "build_delivery_card_content",
    "format_file_size",
    "is_delegation_intent",
    "scan_workspace_artifacts",
]
