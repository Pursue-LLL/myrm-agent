"""JIT Dual Verification Gate package.

[INPUT]
- Package re-exports only; no runtime input.

[OUTPUT]
- The JIT dual-verification gate and its tamper errors.

[POS]
Public surface of the just-in-time dual verification gate.
"""

from myrm_agent_harness.agent.security.jit_gate.gate import (
    AssetTamperedDuringApprovalError,
    JITDualVerificationGate,
    PolicyTightenedAtJITError,
)
from myrm_agent_harness.agent.security.jit_gate.models import (
    AssetContentFingerprint,
    AssetType,
    JITVerificationResult,
)

__all__ = [
    "AssetContentFingerprint",
    "AssetTamperedDuringApprovalError",
    "AssetType",
    "JITDualVerificationGate",
    "JITVerificationResult",
    "PolicyTightenedAtJITError",
]
