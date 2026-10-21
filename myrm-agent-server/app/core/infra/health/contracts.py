"""Contracts for health diagnostics.

[INPUT]
None

[OUTPUT]
- DiagnosticProtocol
- HealthReport

[POS]
Re-exports diagnostic protocols from harness observability.
"""

from __future__ import annotations

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

__all__ = [
    "DiagnosticProtocol",
    "HealthReport",
]
