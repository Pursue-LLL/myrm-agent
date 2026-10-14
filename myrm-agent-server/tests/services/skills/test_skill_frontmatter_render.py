"""Frontmatter rendering for skills materialized from model-generated drafts."""

import pytest
from myrm_agent_harness.api.skills import parse_skill_frontmatter

from app.services.skills.auto_extractor import render_skill_draft_markdown

# Descriptions a model can plausibly emit; unquoted YAML breaks or silently retypes most of these.
_MODEL_DESCRIPTIONS = [
    "Deploy a service: nginx on Ubuntu",
    "Use # for headings in generated docs",
    'Reply with "done" when finished',
    r"Convert C:\temp\new files",
    "First line\nSecond line",
    "- starts like a list item",
    "@mentions and *emphasis* handling",
    "[draft] {template} rendering",
    "yes",
    "null",
    "123",
    "key: value # trailing comment",
    "部署 nginx：一键完成",
]


def _result(**overrides: str) -> dict[str, object]:
    base: dict[str, object] = {
        "has_value": True,
        "type": "skill_draft",
        "skill_name": "deploy-nginx",
        "skill_description": "Deploy nginx",
        "trigger_condition": "When the user asks to deploy nginx",
        "skill_steps": "1. Install\n2. Configure",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("description", _MODEL_DESCRIPTIONS)
def test_rendered_description_round_trips_through_the_skill_parser(description: str) -> None:
    markdown = render_skill_draft_markdown(_result(skill_description=description))

    frontmatter = parse_skill_frontmatter(markdown, "deploy-nginx")

    assert frontmatter.description == description
    assert frontmatter.name == "deploy-nginx"


def test_missing_description_falls_back_to_the_trigger_condition() -> None:
    markdown = render_skill_draft_markdown(_result(skill_description="", trigger_condition="When nginx must be deployed"))

    assert parse_skill_frontmatter(markdown, "deploy-nginx").description == "When nginx must be deployed"


def test_missing_description_and_trigger_fall_back_to_the_name_not_a_placeholder() -> None:
    markdown = render_skill_draft_markdown(_result(skill_description="  ", trigger_condition=""))

    description = parse_skill_frontmatter(markdown, "deploy-nginx").description

    assert description == "deploy-nginx"
    assert "Auto-extracted" not in markdown
