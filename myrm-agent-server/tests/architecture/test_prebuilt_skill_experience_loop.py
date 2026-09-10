"""Architecture guard: Skill pack embedded experience library loop specification and contract.

[INPUT]
- assets/prebuilt_skills/web-scraping/EXPERIENCE.md
- app/core/skills/SKILLS_SYSTEM.md

[OUTPUT]
- Architecture tests ensuring the embedded experience library follows the standard 3-tier structure
  (trigger condition, root cause, and verified prevention), with Read-First and Write-Back loop rules.

[POS]
Architecture test verifying the operational integrity and contract stability of SkillPackEmbeddedExperienceLibraryLoop.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]

_EXPERIENCE_MD = _REPO_ROOT / "assets" / "prebuilt_skills" / "web-scraping" / "EXPERIENCE.md"
_SKILLS_SYSTEM_MD = _SERVER_ROOT / "app" / "core" / "skills" / "SKILLS_SYSTEM.md"

_EXPERIENCE_MARKERS = (
    "技能实战避坑与经验库",
    "Read-First",
    "Write-Back",
    "常见踩坑/错误现象",
    "根本原因 (Root Cause)",
    "防范铁律 / 经检验的最优解",
)

_SYSTEM_DOC_MARKERS = (
    "技能包内嵌经验库自闭环机制",
    "Embedded Experience Library Loop",
    "EXPERIENCE.md",
    "读在前 (Read-First)",
    "写在后 (Write-Back)",
)


def test_web_scraping_experience_file_exists() -> None:
    assert _EXPERIENCE_MD.is_file(), f"Missing experience file: {_EXPERIENCE_MD}"


def test_experience_file_contains_standard_sections() -> None:
    content = _EXPERIENCE_MD.read_text(encoding="utf-8")
    missing = [m for m in _EXPERIENCE_MARKERS if m not in content]
    assert not missing, f"EXPERIENCE.md is missing standard markers: {missing}"


def test_skills_system_doc_contains_experience_loop_specification() -> None:
    content = _SKILLS_SYSTEM_MD.read_text(encoding="utf-8")
    missing = [m for m in _SYSTEM_DOC_MARKERS if m not in content]
    assert not missing, f"SKILLS_SYSTEM.md is missing experience loop markers: {missing}"
