"""Machines service package.

[INPUT]
- app.services.machines.machine_service::MachineService (POS: Process-local machine registry behind the machines API: starts with two sample nodes whose metrics are fixed values (nothing collects telemetry), builds the registration command around a fresh token that it neither stores nor verifies, and switches a node and its takeover session between agent and human control in memory only.)
- app.services.machines.machine_types::MachineMetrics, MachineNode, MachinePlatform, MachineStatus, RegistrationTokenResponse, TakeoverActionRequest, TakeoverSession, TakeoverState (POS: Contract layer of the machines service: the platform, node-status and takeover-state enums plus the telemetry, node, registration-command and takeover-session models shared by the service and the API router.)

[OUTPUT]
- MachineService: the in-memory machine registry service
- MachineMetrics, MachineNode, MachinePlatform, MachineStatus, RegistrationTokenResponse, TakeoverActionRequest, TakeoverSession, TakeoverState: the machine, telemetry, registration-command and takeover models

[POS]
Package facade of the machines service: exposes the service singleton and the machine, metrics, registration-command and
takeover-session models.
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
