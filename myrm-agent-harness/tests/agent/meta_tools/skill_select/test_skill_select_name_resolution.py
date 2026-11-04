"""skill_select_tool maps the name a model writes onto the one bound skill it means.

The catalog lists a skill under one name (``data-analysis``). A model may write it with the ``_skill``
suffix, other casing or underscores, and a continued conversation carries names from older catalogs.
The resolver behind ``[use <name>]`` maps those spellings onto the listed skill and never guesses
between two; the tool's own text must not promise a spelling the catalog does not use. A skill named
more than once in one call, under any of those spellings, loads its SOP once.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from myrm_agent_harness.agent.meta_tools.skills.select.skill_select_tool import (
    build_skill_select_static_description,
    create_select_skill_tool,
)
from myrm_agent_harness.agent.skill_agent.context import get_loaded_skills, reset_loaded_skills
from myrm_agent_harness.agent.skills.runtime.session_skills_rehydrate import (
    collect_loaded_skill_names_from_messages,
    rehydrate_loaded_skills_from_history,
)
from myrm_agent_harness.backends.skills.types import SkillInstance, SkillInstanceConfig, SkillMetadata

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_TOOL_MODULE = "myrm_agent_harness.agent.meta_tools.skills.select.skill_select_tool"
_CONTEXT_MODULE = "myrm_agent_harness.agent.skill_agent.context"


def _skill(name: str) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=f"{name} skill",
        storage_skill_id=name,
        storage_path=f"/skills/{name}",
    )


def _instance(skill: SkillMetadata) -> SkillInstance:
    now = datetime.now(UTC)
    config = SkillInstanceConfig(instance_name="work", skill_name=skill.name, created_at=now, updated_at=now)
    return SkillInstance(metadata=skill, instance_name="work", config=config, state={})


async def _select(
    skills: list[SkillMetadata],
    written: str,
    *,
    loaded: list[SkillMetadata] | None = None,
    skill_instances: dict[str, SkillInstance] | None = None,
) -> tuple[str, AsyncMock, MagicMock]:
    """Select ``written`` once; returns the tool result, the SOP loader mock and the loaded-skill registrar mock."""
    with (
        patch(f"{_CONTEXT_MODULE}.get_loaded_skills", return_value=loaded or []),
        patch(f"{_CONTEXT_MODULE}.add_loaded_skill") as add_loaded,
        patch(f"{_TOOL_MODULE}.get_skill_document", AsyncMock(return_value="# SOP body")) as get_document,
        patch(f"{_TOOL_MODULE}.build_reload_summary_with_index", AsyncMock(return_value="already loaded")),
    ):
        tool = create_select_skill_tool(skills, AsyncMock(), skill_instances)
        result = await tool.ainvoke({"skill_names": [written], "reason": "testing"})
    return result, get_document, add_loaded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "written",
    [
        "data-analysis",
        "data_analysis_skill",
        "Data-Analysis",
        "data_analysis",
        "data-analysis_skill",
        " data-analysis ",
    ],
)
async def test_every_spelling_of_a_catalog_name_loads_that_skill(written: str) -> None:
    skill = _skill("data-analysis")

    result, get_document, add_loaded = await _select([skill, _skill("deep-research")], written)

    get_document.assert_awaited_once()
    assert get_document.await_args is not None
    assert get_document.await_args.args[0] is skill
    add_loaded.assert_called_once_with(skill)
    assert 'status="ready"' in result


@pytest.mark.asyncio
async def test_a_skill_loaded_earlier_is_recognised_under_another_spelling() -> None:
    skill = _skill("data-analysis")

    result, get_document, add_loaded = await _select([skill], "data_analysis_skill", loaded=[skill])

    get_document.assert_not_awaited()
    add_loaded.assert_not_called()
    assert "already loaded" in result


@pytest.mark.asyncio
async def test_skill_instance_is_found_by_the_listed_name() -> None:
    skill = _skill("data-analysis")
    instance = _instance(skill)

    _, get_document, _ = await _select([skill], "data_analysis_skill", skill_instances={"data-analysis": instance})

    assert get_document.await_args is not None
    assert get_document.await_args.kwargs["skill_instance"] is instance


@pytest.mark.asyncio
async def test_two_skills_behind_one_spelling_are_never_guessed() -> None:
    skills = [_skill("foo-bar"), _skill("foo_bar_skill")]

    result, get_document, add_loaded = await _select(skills, "foo_bar")

    get_document.assert_not_awaited()
    add_loaded.assert_not_called()
    assert "not found" in result
    assert 'status="error"' in result


@pytest.mark.asyncio
async def test_unknown_name_reports_the_listed_names() -> None:
    result, get_document, _ = await _select([_skill("data-analysis")], "no-such-skill")

    get_document.assert_not_awaited()
    assert "not found. Available: [data-analysis]" in result


@pytest.mark.asyncio
async def test_a_skill_picked_by_another_spelling_is_restored_on_the_next_turn() -> None:
    skill = _skill("data-analysis")
    written = "data_analysis_skill"
    result, _, _ = await _select([skill], written)
    history = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "skill_select_tool",
                    "args": {"skill_names": [written], "reason": "testing"},
                    "id": "tc1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content=result, tool_call_id="tc1", name="skill_select_tool"),
    ]

    assert collect_loaded_skill_names_from_messages(history) == [written]
    assert rehydrate_loaded_skills_from_history(history, [skill]) == [skill]


@pytest.mark.parametrize(("locale", "stale_promise"), [(None, "_skill suffix"), ("zh-CN", "_skill 后缀")])
def test_tool_text_does_not_promise_a_name_suffix(locale: str | None, stale_promise: str) -> None:
    assert stale_promise not in build_skill_select_static_description(locale)


def test_name_parameter_asks_for_the_catalog_spelling() -> None:
    tool = create_select_skill_tool([_skill("data-analysis")], AsyncMock())

    description = tool.args["skill_names"]["description"]

    assert "end with _skill" not in description
    assert "exactly as the catalog" in description


async def _select_in_run_scope(
    skills: list[SkillMetadata], written: list[str], documents: Callable[..., Awaitable[str]]
) -> str:
    """One call over the run's real loaded-skills scope; only the SOP loader and the reload summary are stubbed."""
    reset_loaded_skills()
    with (
        patch(f"{_TOOL_MODULE}.get_skill_document", documents),
        patch(f"{_TOOL_MODULE}.build_reload_summary_with_index", AsyncMock(return_value="already loaded")),
    ):
        tool = create_select_skill_tool(skills, AsyncMock())
        result = await tool.ainvoke({"skill_names": written, "reason": "testing"})
    assert isinstance(result, str)
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "written",
    [
        ["data-analysis", "data-analysis"],
        ["data-analysis", "data_analysis_skill"],
        ["data-analysis", "Data-Analysis", "data_analysis_skill"],
    ],
)
async def test_a_skill_named_more_than_once_in_a_call_loads_its_sop_once(written: list[str]) -> None:
    documents = AsyncMock(return_value="# SOP body")

    result = await _select_in_run_scope([_skill("data-analysis"), _skill("deep-research")], written, documents)

    documents.assert_awaited_once()
    assert result.count("# SOP body") == 1
    assert result.count("already loaded") == len(written) - 1
    assert result.count('status="ready"') == len(written)
    assert [skill.name for skill in get_loaded_skills()] == ["data-analysis"]


@pytest.mark.asyncio
async def test_two_different_skills_in_a_call_both_load() -> None:
    documents = AsyncMock(return_value="# SOP body")

    result = await _select_in_run_scope(
        [_skill("data-analysis"), _skill("deep-research")], ["data-analysis", "deep-research"], documents
    )

    assert documents.await_count == 2
    assert result.count("# SOP body") == 2
    assert [skill.name for skill in get_loaded_skills()] == ["data-analysis", "deep-research"]


@pytest.mark.asyncio
async def test_a_failed_load_does_not_stop_the_next_spelling_from_loading() -> None:
    documents = AsyncMock(side_effect=["", "# SOP body"])

    result = await _select_in_run_scope([_skill("data-analysis")], ["data-analysis", "data_analysis_skill"], documents)

    assert documents.await_count == 2
    assert result.count("# SOP body") == 1
    assert "already loaded" not in result
    assert result.count('status="error"') == 1
    assert [skill.name for skill in get_loaded_skills()] == ["data-analysis"]


@pytest.mark.asyncio
async def test_a_skill_joins_the_loaded_scope_only_after_its_sop_is_fetched() -> None:
    """The scope feeds the skill-boundary guardrail, so no skill may enter it before its SOP is delivered."""
    scope_while_fetching: list[list[str]] = []

    async def documents(*_args: object, **_kwargs: object) -> str:
        scope_while_fetching.append([skill.name for skill in get_loaded_skills()])
        return "# SOP body"

    await _select_in_run_scope([_skill("data-analysis")], ["data-analysis"], documents)

    assert scope_while_fetching == [[]]
    assert [skill.name for skill in get_loaded_skills()] == ["data-analysis"]
