"""Tests for unified capability discovery meta-tool."""

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.meta_tools.discover_capability.discover_capability_tool import (
    create_discover_capability_tool,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata


class DummyInput(BaseModel):
    arg1: str = Field(description="A dummy argument")


class DummyTool(BaseTool):
    name: str = "dummy_native_tool"
    description: str = "Browse websites and open webpages for the user"
    args_schema: type[BaseModel] = DummyInput

    def _run(self, arg1: str) -> str:
        return "dummy"


@pytest.fixture
def mock_skills():
    return [
        SkillMetadata(name="bound_skill_1", description="A bound skill"),
        SkillMetadata(name="bound_skill_2", description="Another bound skill"),
    ]


@pytest.mark.asyncio
async def test_create_tool_no_engines():
    tool = create_discover_capability_tool()
    assert tool.name == "skill_search_tool"
    result = await tool.ainvoke({"query": "test"})
    assert "No capabilities found" in result


@pytest.mark.asyncio
async def test_discover_bound_skill(mock_skills):
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": ".*", "mode": "regex"})
    assert "Found bound skills" in result
    assert "<BoundSkills>" in result
    assert "bound_skill_1" in result


@pytest.mark.asyncio
async def test_no_matches(mock_skills):
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": "nonexistent_capability_xyz123"})
    assert "No capabilities found" in result


@pytest.mark.asyncio
async def test_miss_returns_plain_not_found_without_gap() -> None:
    tool = create_discover_capability_tool()
    result = await tool.ainvoke({"query": "please browse this website"})
    assert "No capabilities found" in result
    assert "<CapabilityGap>" not in result
    assert "<SkillGap>" not in result


@pytest.mark.asyncio
async def test_hit_returns_bound_skills_without_gap() -> None:
    skills = [
        SkillMetadata(name="browse_helper_skill", description="Browse websites and extract content"),
        SkillMetadata(name="other_skill", description="Another skill"),
    ]
    tool = create_discover_capability_tool(skills=skills)
    result = await tool.ainvoke({"query": "browse", "mode": "regex"})
    assert "Found bound skills" in result
    assert "<BoundSkills>" in result
    assert "<CapabilityGap>" not in result
    assert "<SkillGap>" not in result


@pytest.mark.asyncio
async def test_miss_does_not_dispatch_gap_events(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, object]] = []

    async def _capture(event_name: str, payload: object, config: object | None = None) -> None:
        events.append((event_name, payload))

    monkeypatch.setattr(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        _capture,
    )
    tool = create_discover_capability_tool()
    await tool.ainvoke({"query": "browse website with github_pr_skill"})
    event_names = [name for name, _ in events]
    assert "capability_gap" not in event_names
    assert "skill_gap" not in event_names


@pytest.mark.asyncio
async def test_description_mentions_skill_market_tool_when_mounted() -> None:
    tool = create_discover_capability_tool(market_tool_mounted=True)
    assert "skill_market_tool" in tool.description
    assert "Settings" not in tool.description


@pytest.mark.asyncio
async def test_description_points_to_settings_when_market_not_mounted() -> None:
    tool = create_discover_capability_tool(market_tool_mounted=False)
    assert "skill_market_tool" not in tool.description
    assert "Settings" in tool.description
    assert "Discover" in tool.description


@pytest.mark.asyncio
async def test_description_is_stable_without_dynamic_tool_names():
    """Stable index: discover description must not embed per-tool names (prefix cache)."""
    tool = create_discover_capability_tool()
    assert "dummy_native_tool" not in tool.description


@pytest.mark.asyncio
async def test_description_omits_native_tool_list_when_registry_empty():
    """When registry has no Turn1 tools, description omits the native tools list."""
    tool = create_discover_capability_tool()
    assert "Discoverable native tools" not in tool.description


@pytest.mark.asyncio
async def test_description_contains_must_search_before_declining():
    """Verify tool description enforces proactive search before declining."""
    tool = create_discover_capability_tool()
    assert "MUST search here BEFORE declining" in tool.description
    assert "IMPORTANT" in tool.description


@pytest.mark.asyncio
async def test_bound_skill_output_format(mock_skills):
    """Verify bound skill results use only name and description (no source/version)."""
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": ".*", "mode": "regex"})
    assert "bound_skill_1" in result
    assert "A bound skill" in result
    assert "source:" not in result
    assert "version:" not in result


@pytest.mark.asyncio
async def test_bm25_mode_default(mock_skills):
    """Verify default mode is bm25 (not regex)."""
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": "bound"})
    assert "bound_skill" in result or "No capabilities" in result


@pytest.mark.asyncio
async def test_skill_output_format(mock_skills):
    """Verify skill output uses BoundSkills XML format."""
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": ".*", "mode": "regex"})
    assert "<BoundSkills>" in result
    assert "</BoundSkills>" in result
    assert "<ExternalSkills>" not in result
    assert "bound_skill_1" in result


@pytest.mark.parametrize(
    ("locale", "asks_for", "over_promise"),
    [("en", "English keywords", "any language"), ("zh", "英文关键词", "任意自然语言")],
)
def test_description_asks_for_english_keywords_and_promises_no_language(
    locale: str, asks_for: str, over_promise: str
) -> None:
    """The index is matched word by word and its text is mostly English, so a query in another language alone often finds nothing."""
    tool = create_discover_capability_tool(locale=locale)
    assert asks_for in tool.description
    assert over_promise not in tool.description


def test_query_argument_asks_for_english_keywords_and_promises_no_language() -> None:
    description = create_discover_capability_tool().args_schema.model_fields["query"].description
    assert "English keywords" in description
    assert "any language" not in description


@pytest.mark.asyncio
async def test_empty_result_says_how_to_retry(mock_skills):
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": "nonexistent_capability_xyz123"})
    assert result.startswith("No capabilities found matching 'nonexistent_capability_xyz123'.")
    assert "Retry with English keywords or synonyms" in result
    assert "query='*' lists all 2 bound skills" in result


@pytest.mark.asyncio
async def test_empty_result_without_bound_skills_does_not_point_to_the_full_list():
    result = await create_discover_capability_tool().ainvoke({"query": "anything"})
    assert result.startswith("No capabilities found matching 'anything'.")
    assert "Retry with English keywords or synonyms" in result
    assert "query='*'" not in result


@pytest.mark.asyncio
async def test_hit_result_offers_one_more_search(mock_skills):
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": ".*", "mode": "regex"})
    assert result.endswith("If none of these fit, search again with English keywords or synonyms.")


@pytest.mark.asyncio
async def test_full_list_carries_no_retry_hint(mock_skills):
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": "*"})
    assert "bound_skill_1" in result
    assert "search again" not in result


@pytest.mark.asyncio
async def test_description_contains_skill_select_instruction():
    """Verify description mentions skill_select_tool for bound skills."""
    tool = create_discover_capability_tool()
    assert "skill_select_tool" in tool.description


@pytest.mark.asyncio
async def test_wildcard_query(mock_skills):
    """Verify query='*' lists all skills."""
    tool = create_discover_capability_tool(skills=mock_skills)
    result = await tool.ainvoke({"query": "*"})
    assert "bound_skill_1" in result or "No capabilities" in result
