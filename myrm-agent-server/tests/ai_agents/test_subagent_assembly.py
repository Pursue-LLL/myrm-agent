"""Shared subagent assembly steps: tool boundary, memory_search_tool rebinding and the write backend."""

from types import SimpleNamespace

import pytest

from app.ai_agents.subagent_assembly import (
    apply_subagent_memory_search_rebind,
    filter_tools_by_profile,
    rebind_subagent_memory_search_tool,
)


def test_filter_tools_by_profile_respects_enabled_groups() -> None:
    tools = [
        SimpleNamespace(name="memory_search_tool"),
        SimpleNamespace(name="browser_navigate_tool"),
        SimpleNamespace(name="bash"),
    ]
    filtered = filter_tools_by_profile(tools, ("memory",))
    assert [tool.name for tool in filtered] == ["memory_search_tool", "bash"]


def test_filter_tools_by_profile_enables_all_builtin_groups() -> None:
    tools = [
        SimpleNamespace(name="web_search_tool"),
        SimpleNamespace(name="browser_navigate_tool"),
        SimpleNamespace(name="file_read_tool"),
        SimpleNamespace(name="bash_code_execute_tool"),
        SimpleNamespace(name="computer_use_tool"),
        SimpleNamespace(name="memory_search_tool"),
        SimpleNamespace(name="kanban_list_tasks_tool"),
        SimpleNamespace(name="wiki_search_tool"),
    ]
    enabled = (
        "web_search",
        "browser",
        "file_ops",
        "code_execute",
        "computer_use",
        "memory",
        "kanban",
        "wiki",
    )
    filtered = filter_tools_by_profile(tools, enabled)
    assert len(filtered) == len(tools)


def test_rebind_subagent_memory_search_tool_skips_non_memory_manager() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_subagent_memory_search_tool(
        tools,
        memory_manager=SimpleNamespace(),
    )
    assert tools[0].marker == "parent"


def test_rebind_subagent_memory_search_tool_noop_when_rebuild_missing(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    def fake_create_memory_tools(*args: object, **kwargs: object) -> list[object]:
        return [SimpleNamespace(name="memory_save_tool")]

    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_subagent_memory_search_tool(
        tools,
        memory_manager=FakeMemoryManager(),
    )
    assert tools[0].marker == "parent"


def test_rebind_subagent_memory_search_tool_noop_when_tool_absent(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    tools: list[object] = [SimpleNamespace(name="bash")]
    rebind_subagent_memory_search_tool(
        tools,
        memory_manager=FakeMemoryManager(),
    )
    assert tools[0].name == "bash"


def test_rebind_subagent_memory_search_tool_replaces_inherited_tool_with_own_memory_search(monkeypatch) -> None:
    class FakeMemoryManager:
        approval_required = False

    captured: dict[str, object] = {}

    def fake_create_memory_tools(
        manager: object,
        recall_mode: object = None,
        *,
        search_policy: object = None,
        search_backends: object = None,
        description_locale: str | None = None,
    ) -> list[object]:
        captured.update(
            manager=manager,
            search_policy=search_policy,
            search_backends=search_backends,
            description_locale=description_locale,
        )
        return [SimpleNamespace(name="memory_search_tool", marker="rebound")]

    import myrm_agent_harness.toolkits as toolkits_module
    import myrm_agent_harness.toolkits.memory.manager as memory_manager_module

    monkeypatch.setattr(toolkits_module, "create_memory_tools", fake_create_memory_tools)
    monkeypatch.setattr(memory_manager_module, "MemoryManager", FakeMemoryManager)

    memory_manager = FakeMemoryManager()
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]

    rebind_subagent_memory_search_tool(tools, memory_manager=memory_manager, description_locale="zh")

    assert [(tool.name, tool.marker) for tool in tools] == [("memory_search_tool", "rebound")]
    # No policy or backends: the harness default searches the subagent's own memory only.
    assert captured == {
        "manager": memory_manager,
        "search_policy": None,
        "search_backends": None,
        "description_locale": "zh",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("corpus", ["sessions", "wiki"])
async def test_default_memory_search_tool_does_not_search_past_conversations_or_wiki(corpus: str) -> None:
    from myrm_agent_harness.toolkits import create_memory_tools

    class FakeMemoryManager:
        approval_required = False
        last_retrieval_trace = None

        async def search(self, *args: object, **kwargs: object) -> list[object]:
            return []

        @property
        def active_session(self) -> None:
            return None

    tools = create_memory_tools(FakeMemoryManager())
    search_tool = next(tool for tool in tools if tool.name == "memory_search_tool")

    result = await search_tool.ainvoke({"query": "last quote", "corpus": corpus})

    assert "disabled" in result.lower() or "not enabled" in result.lower()


def test_apply_subagent_memory_search_rebind_skips_without_memory_group() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_calls: list[object] = []

    def _track_rebind(*args: object, **kwargs: object) -> None:
        rebind_calls.append((args, kwargs))

    import app.ai_agents.subagent_assembly as assembly_module

    original = assembly_module.rebind_subagent_memory_search_tool
    assembly_module.rebind_subagent_memory_search_tool = _track_rebind  # type: ignore[assignment]
    try:
        apply_subagent_memory_search_rebind(
            tools,
            parent_agent=SimpleNamespace(),
            memory_manager=SimpleNamespace(),
            enabled_builtin=("web_search",),
        )
    finally:
        assembly_module.rebind_subagent_memory_search_tool = original  # type: ignore[assignment]

    assert rebind_calls == []
    assert tools[0].marker == "parent"


def test_apply_subagent_memory_search_rebind_skips_without_manager() -> None:
    tools: list[object] = [SimpleNamespace(name="memory_search_tool", marker="parent")]
    rebind_calls: list[object] = []

    def _track_rebind(*args: object, **kwargs: object) -> None:
        rebind_calls.append((args, kwargs))

    import app.ai_agents.subagent_assembly as assembly_module

    original = assembly_module.rebind_subagent_memory_search_tool
    assembly_module.rebind_subagent_memory_search_tool = _track_rebind  # type: ignore[assignment]
    try:
        apply_subagent_memory_search_rebind(
            tools,
            parent_agent=SimpleNamespace(),
            memory_manager=None,
            enabled_builtin=("memory",),
        )
    finally:
        assembly_module.rebind_subagent_memory_search_tool = original  # type: ignore[assignment]

    assert rebind_calls == []


def test_subagent_write_backend_none_without_skill_manage_tool() -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.subagent_assembly import subagent_write_backend

    config = SubagentConfig(display_name="Researcher", system_prompt="You research.")
    assert subagent_write_backend(config) is None


def test_subagent_write_backend_present_when_skill_manage_allowed() -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    from app.ai_agents.subagent_assembly import subagent_write_backend

    config = SubagentConfig(
        display_name="Author",
        system_prompt="You write skills.",
        tools=["skill_manage_tool"],
    )
    assert subagent_write_backend(config) is not None
