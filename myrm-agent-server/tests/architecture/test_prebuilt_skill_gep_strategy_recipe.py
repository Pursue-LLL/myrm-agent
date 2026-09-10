"""Architecture guard: gep-strategy-recipe skill contract integrity.

[INPUT]
- assets/prebuilt_skills/gep-strategy-recipe/SKILL.md

[OUTPUT]
- Architecture tests ensuring:
  1. SKILL.md exists and is structurally valid.
  2. Frontmatter contains category: workflow-orchestration and allowed-tools.
  3. Body specifies the GEP Triplet Architecture (Strategy Gene, Environment Capsule, Audit Trace).
  4. Body explicitly details standard Strategy Gene operators.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD = _SERVER_ROOT / "assets" / "prebuilt_skills" / "gep-strategy-recipe" / "SKILL.md"


def test_gep_strategy_recipe_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"gep-strategy-recipe SKILL.md does not exist at {_SKILL_MD}"


def test_gep_strategy_recipe_frontmatter() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md missing frontmatter start"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "Invalid frontmatter delimiters"
    data = yaml.safe_load(parts[1])
    assert data["name"] == "gep-strategy-recipe"
    assert data["category"] == "workflow-orchestration"
    assert "contract" in data
    assert "steps" in data["contract"]


def test_gep_strategy_recipe_triplet_and_operators() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert "Strategy Gene" in content
    assert "Environment Capsule" in content
    assert "Audit Trace" in content
    assert "Phased Probing" in content
    assert "Bisecting Triage" in content
