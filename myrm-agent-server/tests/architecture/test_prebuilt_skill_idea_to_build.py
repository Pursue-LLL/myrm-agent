"""Architecture guard: idea-to-build skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/idea-to-build/SKILL.md

[OUTPUT]
- Architecture tests ensuring idea-to-build skill retains:
  1. Dual pipeline modes (Lite Quick-Capture & Full 5-Stage Specification).
  2. The 5 staged artifact contracts (01-product-intent, 02-functional-spec, 03-tech-architecture, 04-task-breakdown, 05-agent-build-handoff).
  3. Spec Review Gate with mandatory checks (Non-Goals, Acceptance Criteria, Decoupling).
  4. Core design axiom separating product thinking from implementation thinking.

[POS]
Architecture test verifying the operational integrity and contract stability of the idea-to-build prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "idea-to-build"
    / "SKILL.md"
)

_CORE_AXIOM_MARKERS = (
    "idea-to-build",
    "Separate Product Thinking from Implementation Thinking",
    "Lite Quick-Capture",
    "Full 5-Stage Staged Specification",
)

_STAGED_ARTIFACT_MARKERS = (
    "01-product-intent.md",
    "02-functional-spec.md",
    "03-tech-architecture.md",
    "04-task-breakdown.md",
    "05-agent-build-handoff.md",
)

_REVIEW_GATE_MARKERS = (
    "Spec Review Gate",
    "Non-Goals Gate",
    "Acceptance Criteria Gate",
    "Decoupling Gate",
)


def test_idea_to_build_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"Skill file does not exist at {_SKILL_MD}"


def test_idea_to_build_core_axiom_markers() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_AXIOM_MARKERS:
        assert marker in content, f"Missing core axiom marker: {marker}"


def test_idea_to_build_staged_artifacts_and_gate() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _STAGED_ARTIFACT_MARKERS:
        assert marker in content, f"Missing staged artifact marker: {marker}"
    for marker in _REVIEW_GATE_MARKERS:
        assert marker in content, f"Missing review gate marker: {marker}"
