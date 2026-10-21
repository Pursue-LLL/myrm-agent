"""Architecture guard: mcp-command-center skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/mcp-command-center/SKILL.md

[OUTPUT]
- Architecture tests ensuring mcp-command-center skill retains:
  1. Pre-call heartbeat & health probe gate (fast failure <= 2000ms).
  2. Circuit breaker state machine (HEALTHY, DEGRADED, TRIPPED, HALF-OPEN).
  3. Token budget and payload truncation boundaries.
  4. 30-day cost and health audit report deliverables.

[POS]
Architecture test verifying the operational integrity and contract stability of the mcp-command-center prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "mcp-command-center"
    / "SKILL.md"
)

_CORE_GOVERNANCE_MARKERS = (
    "mcp-command-center",
    "Pre-Call Heartbeat & Probe Gate",
    "Payload Guardrails & Token Throttling",
    "Event Ledger & Latency Metrics",
    "30-Day Cost & Health Audit Dashboard",
)

_CIRCUIT_BREAKER_MARKERS = (
    "HEALTHY",
    "DEGRADED",
    "TRIPPED",
    "HALF-OPEN",
)

_BUDGET_MARKERS = (
    "Mandatory Truncation",
    "Payload Throttled",
)


def test_mcp_command_center_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"Skill file does not exist at {_SKILL_MD}"


def test_mcp_command_center_governance_markers() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_GOVERNANCE_MARKERS:
        assert marker in content, f"Missing governance marker: {marker}"


def test_mcp_command_center_circuit_breaker_and_budget() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CIRCUIT_BREAKER_MARKERS:
        assert marker in content, f"Missing circuit breaker marker: {marker}"
    for marker in _BUDGET_MARKERS:
        assert marker in content, f"Missing budget marker: {marker}"
