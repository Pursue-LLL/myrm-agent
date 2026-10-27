"""Orchestration control plane — signals (not Action Tools).

[OUTPUT]
- signals: JSON schema contracts intercepted by orchestrators (DR, Verifier)

[POS]
Separates control-plane LLM signals from Action Tools in ``tool_management/``.
Action Tools live in ``ToolRegistry`` + ``_TOOL_LAYERS``; orchestration signals do not.
"""

from .signals.catalog import ORCHESTRATION_SIGNAL_NAMES

__all__ = [
    "ORCHESTRATION_SIGNAL_NAMES",
]
