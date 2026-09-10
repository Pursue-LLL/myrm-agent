"""Architecture guard: viral-quote-discovery skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/viral-quote-discovery/SKILL.md

[OUTPUT]
- Architecture tests ensuring viral-quote-discovery skill retains 4-dimensional viral scoring radar,
  4-step discovery workflow, threshold filters, attribution rules, and deliverable contract.

[POS]
Architecture test verifying the operational integrity and contract stability of the viral-quote-discovery prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "viral-quote-discovery"
    / "SKILL.md"
)

_RADAR_MARKERS = (
    "viral-quote-discovery",
    "4-Dimensional Viral Scoring Radar",
    "Emotional Resonance",
    "Counter-Intuitive Contrast",
    "Syntactic Economy",
    "Memetic & Shareability Potential",
)

_SOP_MARKERS = (
    "Step 1: Ingestion & Boundary Parsing",
    "Step 2: Candidate Scoring & Filtering",
    "Step 3: Repurposing Packaging",
    "Step 4: Structured Deliverable Export",
)

_SAFETY_MARKERS = (
    "Context Fidelity",
    "Attribution",
    "Actionable Follow-up",
)

_TOOL_MARKERS = (
    "file_write_tool",
    "file_read_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing viral-quote-discovery skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_viral_quote_discovery_skill_exists_and_bounded(skill_text: str) -> None:
    """Skill file exists, is non-empty, and bounded in size."""
    assert len(skill_text) > 500, "Skill file is unexpectedly short"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"Skill exceeds budget ({len(skill_text)} > {_MAX_SKILL_CHARS}); keep it focused"
    )


def test_viral_quote_discovery_skill_declares_radar_dimensions(skill_text: str) -> None:
    """Skill strictly specifies the 4-dimensional viral scoring radar."""
    for marker in _RADAR_MARKERS:
        assert marker in skill_text, f"Missing viral radar marker: {marker}"


def test_viral_quote_discovery_skill_declares_sop_stages(skill_text: str) -> None:
    """Skill strictly specifies the 4-step discovery workflow."""
    for marker in _SOP_MARKERS:
        assert marker in skill_text, f"Missing SOP stage marker: {marker}"


def test_viral_quote_discovery_skill_declares_safety_rules(skill_text: str) -> None:
    """Skill strictly specifies safety and attribution rules."""
    for marker in _SAFETY_MARKERS:
        assert marker in skill_text, f"Missing safety rule marker: {marker}"


def test_viral_quote_discovery_skill_declares_allowed_tools(skill_text: str) -> None:
    """Skill explicitly declares tools in allowed-tools."""
    for marker in _TOOL_MARKERS:
        assert marker in skill_text, f"Missing expected tool in allowed-tools: {marker}"
