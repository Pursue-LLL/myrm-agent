"""Delegation coordination, in-flight steering pipeline, and remote approval relay subsystem.

[INPUT]
- .delegation_coordinator::DelegationCoordinator
- .delegation_delivery::build_approval_card_content, build_delivery_card_content
- .delegation_ingress::DelegationIngressGuard, build_delegation_task
- .delegation_models::ApprovalRequest, ApprovalResponse, DelegationTask, DeliveryArtifact

[OUTPUT]
- Public exports for delegation subsystem

[POS]
Subsystem public API and data models for channel task delegation, approval, and delivery.
"""

from .delegation_coordinator import DelegationCoordinator
from .delegation_delivery import (
    build_approval_card_content,
    build_delivery_card_content,
    format_file_size,
    scan_workspace_artifacts,
)
from .delegation_ingress import (
    DelegationIngressGuard,
    build_delegation_task,
    build_receipt_card_content,
    is_delegation_intent,
)
from .delegation_models import (
    ApprovalRequest,
    ApprovalResponse,
    DelegationReceipt,
    DelegationStatus,
    DelegationTask,
    DeliveryArtifact,
    ProgressBeacon,
    RiskLevel,
    SteeringMessage,
)

__all__ = [
    "ApprovalRequest",
    "ApprovalResponse",
    "DelegationCoordinator",
    "DelegationIngressGuard",
    "DelegationReceipt",
    "DelegationStatus",
    "DelegationTask",
    "DeliveryArtifact",
    "ProgressBeacon",
    "RiskLevel",
    "SteeringMessage",
    "build_approval_card_content",
    "build_delegation_task",
    "build_delivery_card_content",
    "build_receipt_card_content",
    "format_file_size",
    "is_delegation_intent",
    "scan_workspace_artifacts",
]

