"""Architecture guard: cross-harness-skill-discovery skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/cross-harness-skill-discovery/SKILL.md

[OUTPUT]
- Architecture tests ensuring cross-harness-skill-discovery skill retains:
  1. Multi-source search paths (Cursor, Claude, OpenClaw, Windsurf).
  2. 4-stage discovery and normalization pipeline.
  3. Namespace collision prevention and read-only source isolation.
  4. Dialect normalization and in-memory hot registration.

[POS]
Architecture test verifying the operational integrity and contract stability of the cross-harness-skill-discovery prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "cross-harness-skill-discovery"
    / "SKILL.md"
)

_CORE_HARNESS_MARKERS = (
    "cross-harness-skill-discovery",
    "Cursor",
    "Claude",
    "OpenClaw",
    "~/.cursor/skills",
    "~/.claude/skills",
)

_LIFECYCLE_MARKERS = (
    "Multi-Root Filesystem Probing",
    "Dialect Normalization",
    "Namespace Collision & Source Isolation",
    "In-Memory Hot Registration",
)

_SECURITY_INVARIANT_MARKERS = (
    "Strict Read-Only Enforcement",
    "Fail-Safe Dialect Fallback",
)


def test_cross_harness_skill_discovery_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"Skill file does not exist at {_SKILL_MD}"


def test_cross_harness_skill_discovery_harness_markers() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_HARNESS_MARKERS:
        assert marker in content, f"Missing core harness marker: {marker}"


def test_cross_harness_skill_discovery_lifecycle_and_invariants() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _LIFECYCLE_MARKERS:
        assert marker in content, f"Missing lifecycle marker: {marker}"
    for marker in _SECURITY_INVARIANT_MARKERS:
        assert marker in content, f"Missing security invariant marker: {marker}"
