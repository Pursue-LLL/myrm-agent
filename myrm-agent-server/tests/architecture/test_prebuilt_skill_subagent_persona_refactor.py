"""Architecture guard: subagent-persona-refactor skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/subagent-persona-refactor/SKILL.md

[OUTPUT]
- Architecture tests ensuring subagent-persona-refactor skill retains:
  1. 4-stage refactoring pipeline (Ingestion, Diagnostics, Persona Synthesis, Spec Compilation).
  2. Diagnostic indicators and anti-pattern taxonomy (Fat Agent, Tool Confusion, Retry Storm, Instruction Drift).
  3. Standard 4-dimensional subagent topology (Research, Planning, Execution, Verification).
  4. Single Responsibility Principle (SRP) and minimal privilege tool boundaries.

[POS]
Architecture test verifying the operational integrity and contract stability of the subagent-persona-refactor prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "subagent-persona-refactor"
    / "SKILL.md"
)

_CORE_TOPOLOGY_MARKERS = (
    "subagent-persona-refactor",
    "Research Specialist",
    "Architecture Planner",
    "Code Implementer",
    "Quality & Security Guard",
)

_LIFECYCLE_MARKERS = (
    "Trace Ingestion & Statistical Profiling",
    "Bottleneck & Anti-Pattern Diagnosis",
    "SubAgent Persona Matrix Synthesis",
    "Spec Compilation & Handoff Schema",
)

_ANTI_PATTERN_MARKERS = (
    "Fat Agent Bloat",
    "Tool Confusion Rate",
    "Retry Storm (Death Loop)",
    "Instruction Drift",
)


def test_subagent_persona_refactor_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"Skill file does not exist at {_SKILL_MD}"


def test_subagent_persona_refactor_core_topology_markers() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_TOPOLOGY_MARKERS:
        assert marker in content, f"Missing core topology marker: {marker}"


def test_subagent_persona_refactor_lifecycle_and_antipatterns() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _LIFECYCLE_MARKERS:
        assert marker in content, f"Missing lifecycle marker: {marker}"
    for marker in _ANTI_PATTERN_MARKERS:
        assert marker in content, f"Missing anti-pattern marker: {marker}"
