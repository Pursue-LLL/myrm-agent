"""SkillAgent skill loading and tool assembly.

Every call to _get_cached_skills fetches from the backend (hot reload); _build_tools mounts
skill_manage_tool from the write backend unless the caller supplied its own, and ``no_builtin_tools`` leaves out the
one built from the write backend while the caller's own stays; the GUI tools snapshot lists the tools the model is
offered. A fresh SkillAgent assigns every attribute the tools mixin declares as its host contract.
"""

from unittest.mock import AsyncMock, create_autospec, patch

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.skills.manage import create_skill_manage_tool
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.skill_agent.tools import SkillAgentToolsMixin
from myrm_agent_harness.agent.skills import SkillMetadata
from myrm_agent_harness.agent.types import AgentRuntimeConfig
from myrm_agent_harness.backends.skills.scanning import ScanningSkillWriteBackend


@pytest.mark.asyncio
async def test_skills_always_fetched_from_backend() -> None:
    """Each call to _get_cached_skills queries the backend (hot-reload support)."""
    mock_skill_backend = AsyncMock()
    mock_skill_backend.list_skills = AsyncMock(
        return_value=[
            SkillMetadata(name="skill1", description="Test skill 1"),
            SkillMetadata(name="skill2", description="Test skill 2"),
        ]
    )

    mock_llm = AsyncMock()

    agent = SkillAgent(llm=mock_llm, skill_backend=mock_skill_backend)

    skills1 = await agent._get_cached_skills()
    assert len(skills1) == 2
    assert mock_skill_backend.list_skills.call_count == 1

    skills2 = await agent._get_cached_skills()
    assert len(skills2) == 2
    assert mock_skill_backend.list_skills.call_count == 2


@pytest.mark.asyncio
async def test_skills_build_tools_calls_backend() -> None:
    """_build_tools fetches skills from backend each time."""
    mock_skill_backend = AsyncMock()
    mock_skill_backend.list_skills = AsyncMock(
        return_value=[
            SkillMetadata(name="test_skill", description="Test skill"),
        ]
    )

    mock_llm = AsyncMock()

    agent = SkillAgent(llm=mock_llm, skill_backend=mock_skill_backend)

    await agent._get_cached_skills()
    assert mock_skill_backend.list_skills.call_count == 1

    tools = await agent._build_tools()
    assert mock_skill_backend.list_skills.call_count == 2
    assert isinstance(tools, list)


@pytest.mark.asyncio
async def test_skills_get_storage_paths_calls_backend() -> None:
    """_get_skill_storage_paths fetches skills from backend each time."""
    mock_skill_backend = AsyncMock()
    mock_skill_backend.list_skills = AsyncMock(
        return_value=[
            SkillMetadata(name="skill1", description="Test skill", storage_path="skill1_storage"),
        ]
    )

    mock_llm = AsyncMock()

    agent = SkillAgent(llm=mock_llm, skill_backend=mock_skill_backend)

    await agent._get_cached_skills()
    assert mock_skill_backend.list_skills.call_count == 1

    paths = await agent._get_skill_storage_paths()
    assert mock_skill_backend.list_skills.call_count == 2
    assert isinstance(paths, list)


@pytest.mark.asyncio
async def test_skills_backend_exception_returns_empty_list() -> None:
    """When backend raises, _get_cached_skills returns empty list."""
    mock_skill_backend = AsyncMock()
    mock_skill_backend.list_skills = AsyncMock(side_effect=Exception("Backend error"))

    mock_llm = AsyncMock()

    agent = SkillAgent(llm=mock_llm, skill_backend=mock_skill_backend)

    skills = await agent._get_cached_skills()
    assert skills == []
    assert mock_skill_backend.list_skills.call_count == 1

    skills2 = await agent._get_cached_skills()
    assert skills2 == []
    assert mock_skill_backend.list_skills.call_count == 2


@pytest.mark.asyncio
async def test_skill_agent_close_triggers_cleanup_tools() -> None:
    """SkillAgent.close() must await cleanup_tools() and reset memory_manager."""
    mock_llm = AsyncMock()
    mock_skill_backend = AsyncMock()
    mock_skill_backend.list_skills = AsyncMock(return_value=[])

    agent = SkillAgent(llm=mock_llm, skill_backend=mock_skill_backend)

    with patch.object(agent, "cleanup_tools", new_callable=AsyncMock) as cleanup_tools:
        await agent.close()

    assert agent.memory_manager is None
    cleanup_tools.assert_awaited_once()


def _skill_agent(
    *,
    write_backend: bool = True,
    skills: list[SkillMetadata] | None = None,
    tools: list[BaseTool] | None = None,
    config: AgentRuntimeConfig | None = None,
) -> SkillAgent:
    skill_backend = AsyncMock()
    skill_backend.list_skills = AsyncMock(return_value=skills or [])
    return SkillAgent(
        llm=AsyncMock(),
        skill_backend=skill_backend,
        write_backend=create_autospec(ScanningSkillWriteBackend, instance=True) if write_backend else None,
        tools=tools,
        config=config,
    )


def test_a_fresh_skill_agent_assigns_every_attribute_the_tools_mixin_declares() -> None:
    """The mixin's class-body annotations are the host contract; mypy cannot see one the host never assigns."""
    agent = SkillAgent(llm=AsyncMock())

    unassigned = [name for name in SkillAgentToolsMixin.__annotations__ if not hasattr(agent, name)]

    assert not unassigned, f"SkillAgent never assigns what SkillAgentToolsMixin declares: {unassigned}"


@pytest.mark.asyncio
async def test_skill_manage_tool_is_mounted_from_the_write_backend() -> None:
    agent = _skill_agent()

    tools = await agent._build_tools()

    assert [t.name for t in tools].count("skill_manage_tool") == 1


@pytest.mark.asyncio
async def test_a_user_provided_skill_manage_tool_is_not_built_a_second_time() -> None:
    own = create_skill_manage_tool(create_autospec(ScanningSkillWriteBackend, instance=True), None)
    agent = _skill_agent(tools=[own])

    with patch("myrm_agent_harness.agent.meta_tools.skills.manage.create_skill_manage_tool") as build:
        tools = await agent._build_tools()

    build.assert_not_called()
    assert [t for t in tools if t.name == "skill_manage_tool"] == [own]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("no_builtin_tools", "host_supplies_it", "mounted"),
    [
        (False, False, True),
        (True, False, False),
        (False, True, True),
        (True, True, True),
    ],
)
async def test_no_builtin_tools_leaves_out_only_the_skill_manage_tool_built_from_the_write_backend(
    no_builtin_tools: bool, host_supplies_it: bool, mounted: bool
) -> None:
    own = create_skill_manage_tool(create_autospec(ScanningSkillWriteBackend, instance=True), None)
    agent = _skill_agent(
        tools=[own] if host_supplies_it else None,
        config=AgentRuntimeConfig(no_builtin_tools=no_builtin_tools),
    )

    names = [t.name for t in await agent._build_tools()]

    assert names.count("skill_manage_tool") == (1 if mounted else 0)
    assert ("bash_code_execute_tool" in names) is not no_builtin_tools


@pytest.mark.asyncio
@pytest.mark.parametrize("no_builtin_tools", [False, True])
async def test_the_tools_snapshot_lists_the_tools_the_model_is_offered(no_builtin_tools: bool) -> None:
    """A catalog too large to list inline mounts ``skill_search_tool``, a built-in the flag leaves out."""
    long_description = "Handles one narrow kind of work that needs its own detailed procedure and checks. " * 4
    skills = [
        SkillMetadata(name=f"skill_{i:03d}", description=long_description, model_invocable=True, available=True)
        for i in range(120)
    ]
    agent = _skill_agent(
        write_backend=False, skills=skills, config=AgentRuntimeConfig(no_builtin_tools=no_builtin_tools)
    )

    offered = sorted(t.name for t in await agent._build_tools())
    listed = sorted(str(item["name"]) for item in agent._emit_tools_snapshot() or [])

    assert listed == offered
    assert ("skill_search_tool" in offered) is not no_builtin_tools


@pytest.mark.asyncio
async def test_the_mounted_skill_manage_tool_speaks_the_prompt_locale() -> None:
    write_backend = create_autospec(ScanningSkillWriteBackend, instance=True)
    english = create_skill_manage_tool(write_backend, None).description
    chinese = create_skill_manage_tool(write_backend, None, locale="zh").description
    assert english != chinese
    agent = _skill_agent(config=AgentRuntimeConfig(prompt_locale="zh"))

    mounted = next(t for t in await agent._build_tools() if t.name == "skill_manage_tool")

    assert mounted.description == chinese


@pytest.mark.asyncio
async def test_mounting_the_skill_manage_tool_leaves_the_skill_select_description_unchanged() -> None:
    skills = [SkillMetadata(name="demo_skill", description="Demo", model_invocable=True, available=True)]

    async def select_description(*, write_backend: bool) -> str:
        agent = _skill_agent(write_backend=write_backend, skills=skills)
        return next(t for t in await agent._build_tools() if t.name == "skill_select_tool").description

    with_manage_tool = await select_description(write_backend=True)

    assert with_manage_tool == await select_description(write_backend=False)
    assert "skill_manage_tool" not in with_manage_tool
