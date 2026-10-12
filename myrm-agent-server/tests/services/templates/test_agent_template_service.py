"""Tests for AgentTemplateService in app.services.templates.

[INPUT]
- app.services.templates::AgentTemplateService
- app.services.templates::CloneTemplateOptions

[OUTPUT]
- Unit tests verifying discovery, categorization, blueprint generation, and cloning

[POS]
Unit test suite for AgentTemplateService under tests/services/templates/.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.templates import (
    CATEGORY_WIKI_BLUEPRINTS,
    AgentTemplateService,
    CloneTemplateOptions,
)


def test_list_templates_returns_valid_prebuilts() -> None:
    """Verify that list_templates correctly parses prebuilt YAML assets."""
    templates = AgentTemplateService.list_templates(accept_language="zh")
    assert len(templates) >= 20, f"Expected at least 20 prebuilt templates, got {len(templates)}"

    # Check categories coverage
    categories = {t.category for t in templates}
    assert "engineering" in categories
    assert "office" in categories
    assert "commerce" in categories
    assert "team" in categories

    # Check every template has non-empty ID and name
    for t in templates:
        assert t.id
        assert t.name
        assert isinstance(t.wiki_blueprint, list)
        assert len(t.wiki_blueprint) > 0


def test_get_template_by_id() -> None:
    """Verify get_template retrieves specific template with wiki blueprint."""
    tmpl = AgentTemplateService.get_template("frontend_development_expert", accept_language="en")
    assert tmpl is not None
    assert tmpl.id == "frontend_development_expert"
    assert tmpl.category == "engineering"
    assert "architecture/" in tmpl.wiki_blueprint

    # Test non-existent template returns None
    assert AgentTemplateService.get_template("non_existent_id") is None


def test_category_wiki_blueprint_mapping() -> None:
    """Verify that all standard categories have explicit wiki directory blueprints."""
    for cat in ("engineering", "office", "commerce", "team", "general"):
        assert cat in CATEGORY_WIKI_BLUEPRINTS
        assert len(CATEGORY_WIKI_BLUEPRINTS[cat]) >= 3


@pytest.mark.asyncio
async def test_clone_and_instantiate_individual_template() -> None:
    """Verify cloning an individual template calls AgentService and enables skills."""
    fake_agent = AsyncMock()
    fake_agent.id = "agent_test_123"
    fake_agent.name = "My Custom Coder"

    with (
        patch("app.services.templates.agent_template_service.ensure_skills_enabled", new_callable=AsyncMock) as mock_skill,
        patch("app.services.agent.agent_service.AgentService.create_agent", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.return_value = fake_agent

        options = CloneTemplateOptions(
            template_id="frontend_development_expert",
            custom_name="My Custom Coder",
            accept_language="en",
            init_wiki_blueprint=True,
        )

        res = await AgentTemplateService.clone_and_instantiate(options)

        mock_skill.assert_awaited_once()
        mock_create.assert_awaited_once()
        assert res["id"] == "agent_test_123"
        assert res["name"] == "My Custom Coder"
        assert res["agent_type"] == "individual"
        assert res["template_id"] == "frontend_development_expert"
        assert res["wiki_blueprint_initialized"] is True


@pytest.mark.asyncio
async def test_clone_and_instantiate_team_template() -> None:
    """Verify cloning a team template creates member agents and leader with rollback guard."""
    with (
        patch("app.services.templates.agent_template_service.ensure_skills_enabled", new_callable=AsyncMock) as mock_skill,
        patch("app.services.agent.agent_service.AgentService.create_agent", new_callable=AsyncMock) as mock_create,
    ):
        mock_create.side_effect = lambda dto: AsyncMock(id=f"id_{dto.name}", name=dto.name)

        options = CloneTemplateOptions(
            template_id="content_creation_squad",
            custom_name="Content Team Alpha",
            accept_language="zh",
            init_wiki_blueprint=True,
        )

        res = await AgentTemplateService.clone_and_instantiate(options)

        mock_skill.assert_awaited_once()
        assert res["agent_type"] == "team"
        assert res["id"] == "id_Content Team Alpha"
        assert res["template_id"] == "content_creation_squad"
        assert len(res["team_member_ids"]) == 3
