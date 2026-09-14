"""Architecture guard: financial analyst prebuilt agent must stay wired to its skill.

[INPUT]
- assets/prebuilt_agents/financial_analyst.yaml
- assets/prebuilt_skills/financial-business-analysis/SKILL.md

[OUTPUT]
- Guard tests ensuring the prebuilt financial analyst agent exists, is valid, and keeps
  its binding to the financial-business-analysis prebuilt skill.

[POS]
Architecture tests protecting the end-to-end wiring between prebuilt agent template and
prebuilt skill asset, preventing silent breakage when skills are renamed or removed.
"""

from __future__ import annotations

import os

import yaml

from app.services.agent.template_utils import PREBUILT_AGENTS_DIR

_FINANCIAL_SKILL_ID = "financial-business-analysis"


def _load_financial_analyst_agent() -> dict:
    agent_path = os.path.join(PREBUILT_AGENTS_DIR, "financial_analyst.yaml")
    assert os.path.isfile(agent_path), f"Missing template: {agent_path}"
    with open(agent_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def test_financial_analyst_agent_exists_and_valid() -> None:
    """The financial analyst template must exist with valid metadata."""
    data = _load_financial_analyst_agent()
    assert data["category"] == "office"
    assert "zh" in data["name"] and "en" in data["name"]
    assert len(data.get("suggestion_prompts", [])) >= 3


def test_financial_analyst_binds_financial_skill() -> None:
    """The prebuilt agent must keep its binding to the financial-business-analysis skill."""
    data = _load_financial_analyst_agent()
    bound_skills = data.get("prebuilt_skill_ids", [])
    assert _FINANCIAL_SKILL_ID in bound_skills, (
        f"financial_analyst.yaml lost its binding to '{_FINANCIAL_SKILL_ID}'; "
        f"current bindings: {bound_skills}"
    )


def test_bound_skills_exist_on_disk() -> None:
    """Every bound prebuilt skill id must point to an existing skill directory."""
    data = _load_financial_analyst_agent()
    skills_root = os.path.join(os.path.dirname(PREBUILT_AGENTS_DIR), "prebuilt_skills")
    for skill_id in data.get("prebuilt_skill_ids", []):
        skill_md = os.path.join(skills_root, skill_id, "SKILL.md")
        assert os.path.isfile(skill_md), (
            f"prebuilt_skill_ids references non-existent skill: {skill_id}"
        )