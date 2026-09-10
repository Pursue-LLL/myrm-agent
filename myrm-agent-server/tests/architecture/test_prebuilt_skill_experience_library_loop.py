"""Architecture guard: office-document skill embedded experience library loop integrity.

[INPUT]
- assets/prebuilt_skills/office-document/EXPERIENCE.md
- assets/prebuilt_skills/office-document/SKILL.md
- app/core/skills/SKILLS_SYSTEM.md

[OUTPUT]
- Architecture tests ensuring the embedded experience library loop specification is met:
  1. EXPERIENCE.md exists in the skill bundle
  2. Experience library loop section is integrated in SKILL.md
  3. EXPERIENCE.md adheres to the standard tripartite structure (Scenario / Pitfall / Best Practice)
"""

from __future__ import annotations

from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SKILL_DIR = _SERVER_ROOT / "assets" / "prebuilt_skills" / "office-document"
_EXPERIENCE_MD = _SKILL_DIR / "EXPERIENCE.md"
_SKILL_MD = _SKILL_DIR / "SKILL.md"
_SKILLS_SYSTEM_MD = _SERVER_ROOT / "app" / "core" / "skills" / "SKILLS_SYSTEM.md"

_CORE_TOPICS = (
    "openpyxl",
    "MergedCell",
    "python-pptx",
    "python-docx",
    "word_wrap",
)

_STRUCTURE_MARKERS = (
    "触发场景",
    "踩坑现象",
    "根因分析",
    "最佳实践",
)


def test_experience_file_exists() -> None:
    assert _EXPERIENCE_MD.is_file(), f"EXPERIENCE.md does not exist at {_EXPERIENCE_MD}"


def test_skill_md_mentions_experience_loop() -> None:
    assert _SKILL_MD.is_file(), f"SKILL.md does not exist at {_SKILL_MD}"
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert "Experience Library Loop" in content
    assert "EXPERIENCE.md" in content
    assert "Read-First" in content
    assert "Write-Back" in content


def test_skills_system_documents_embedded_experience_library() -> None:
    assert _SKILLS_SYSTEM_MD.is_file(), f"SKILLS_SYSTEM.md does not exist at {_SKILLS_SYSTEM_MD}"
    content = _SKILLS_SYSTEM_MD.read_text(encoding="utf-8")
    assert "技能包内嵌经验库自闭环机制" in content
    assert "EXPERIENCE.md" in content


def test_experience_file_contains_structure_and_topics() -> None:
    content = _EXPERIENCE_MD.read_text(encoding="utf-8")
    for topic in _CORE_TOPICS:
        assert topic in content, f"Missing core topic '{topic}' in {_EXPERIENCE_MD}"
    for marker in _STRUCTURE_MARKERS:
        assert marker in content, f"Missing structure marker '{marker}' in {_EXPERIENCE_MD}"
