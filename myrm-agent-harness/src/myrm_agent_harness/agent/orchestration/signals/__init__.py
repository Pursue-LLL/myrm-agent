"""Orchestration signal schemas — control plane, not Action Tools.

[POS]
Re-exports orchestration signal names and schema builders for Verifier
orchestrators (see signals/_ARCH.md).
"""

from .catalog import (
    ORCHESTRATION_SIGNAL_NAMES,
    SUBMIT_VERDICT_SIGNAL,
    VERIFIER_SIGNAL_NAMES,
)
from .verifier import SUBMIT_VERDICT_SIGNAL_NAME, create_submit_verdict_tool

__all__ = [
    "ORCHESTRATION_SIGNAL_NAMES",
    "SUBMIT_VERDICT_SIGNAL",
    "SUBMIT_VERDICT_SIGNAL_NAME",
    "VERIFIER_SIGNAL_NAMES",
    "create_submit_verdict_tool",
]
