"""Skill Sync — cross-device / cross-sandbox skill synchronization.

Provides Protocol-driven bidirectional skill sync. The framework defines the protocols,
the manager, the manifest and a default quality gate; the host application supplies the
transport as a ``SkillSyncProtocol`` implementation.

[OUTPUT]
- SkillSyncProtocol: Protocol for skill sync backends
- SkillQualityGateProtocol: Protocol for push quality gate
- SkillSyncManager: Sync orchestrator
- SkillSyncManifest: Persistent sync state
- ThresholdQualityGate: Default quality gate

[POS]
Skill synchronization module — collective skill evolution enabler.
"""

from .manager import SkillSyncManager
from .manifest import SkillSyncManifest
from .protocols import SkillQualityGateProtocol, SkillSyncProtocol
from .quality_gate import ThresholdQualityGate
from .types import (
    ConflictStrategy,
    GateVerdict,
    PullResult,
    PushResult,
    RemoteSkillEntry,
    SyncDirection,
    SyncStatus,
)

__all__ = [
    "ConflictStrategy",
    "GateVerdict",
    "PullResult",
    "PushResult",
    "RemoteSkillEntry",
    "SkillQualityGateProtocol",
    "SkillSyncManager",
    "SkillSyncManifest",
    "SkillSyncProtocol",
    "SyncDirection",
    "SyncStatus",
    "ThresholdQualityGate",
]
