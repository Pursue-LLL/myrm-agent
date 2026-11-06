"""Orchestration signal name registry — not Action Tools.

[OUTPUT]
- VERIFIER_SIGNAL_NAMES / ORCHESTRATION_SIGNAL_NAMES

[POS]
SSOT for control-plane JSON schemas bound via ``llm.bind_tools()`` and intercepted
by Python orchestrators. Never registered in ``_TOOL_LAYERS`` or ``ToolRegistry``
for default GeneralAgent sessions.
"""

from __future__ import annotations

SUBMIT_VERDICT_SIGNAL = "submit_verdict"

VERIFIER_SIGNAL_NAMES: frozenset[str] = frozenset({SUBMIT_VERDICT_SIGNAL})

ORCHESTRATION_SIGNAL_NAMES: frozenset[str] = frozenset(VERIFIER_SIGNAL_NAMES)
