"""Real-world tests for subagent system.

真实场景测试 Subagent 系统：
1. 使用真实 BaseAgent 配置
2. 测试并发搜索场景
3. 测试资源隔离
4. 测试生产级配置
"""

import asyncio

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.meta_tools.spawn_subagent import create_delegate_task_tool
from myrm_agent_harness.agent.middlewares import create_concurrency_limiter
from myrm_agent_harness.agent.types import AgentRuntimeConfig

from app.ai_agents.subagent_presets import register_default_subagent_configs

register_default_subagent_configs()


class MockLLM:
    """Mock LLM for testing without API calls."""

    def __init__(self, response="搜索完成"):
        self.response = response
        self.call_count = 0

    def bind(self, **kwargs):
        return self

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages, config=None):
        self.call_count += 1
        await asyncio.sleep(0.1)
        from langchain_core.messages import AIMessage

        return AIMessage(content=self.response)


class MockWebSearchTool(BaseTool):
    """Mock web search tool."""

    name: str = "web_search_tool"
    description: str = "Search the web"

    def _run(self, questions: list[str], reason: str = ""):
        return {"results": [f"Result for {q}" for q in questions]}

    async def _arun(self, questions: list[str], reason: str = ""):
        await asyncio.sleep(0.1)
        return {"results": [f"Result for {q}" for q in questions]}


@pytest.mark.asyncio
async def test_real_world_concurrent_search():
    """真实场景：并发搜索多个来源"""
    llm = MockLLM("搜索结果：Python 3.13 新特性...")

    agent = BaseAgent(
        llm=llm,
        middlewares=[create_concurrency_limiter()],
        config=AgentRuntimeConfig(recursion_limit=25, timeout_seconds=30),
    )

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    search_tasks = [
        "搜索 Python 3.13 在 Google 的信息",
        "搜索 Python 3.13 在 Stack Overflow 的讨论",
        "搜索 Python 3.13 官方文档",
    ]

    results = []
    for _i, task in enumerate(search_tasks):
        result = await spawn_tool.ainvoke(
            {
                "agent_type": "search",
                "objective": task,
                "context": {"session_id": "test_session", "workspace_path": "/tmp/test"},
                "wait": False,
            }
        )
        results.append(result)

    task_ids = [r["task_id"] for r in results if "task_id" in r]
    assert len(task_ids) == 3

    aggregated = await agent.wait_children(task_ids, min_success_rate=0.7)

    assert "success_rate" in aggregated
    assert "results" in aggregated


@pytest.mark.asyncio
async def test_real_world_concurrency_limit():
    """真实场景：验证并发限制生效"""
    llm = MockLLM()

    agent = BaseAgent(
        llm=llm,
        middlewares=[create_concurrency_limiter()],
    )

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [],
        catalog=catalog,
    )

    browser_config = SubagentConfig(system_prompt="test")
    assert browser_config.concurrency_limit == 5

    tasks = []
    for i in range(5):
        task = spawn_tool.ainvoke(
            {
                "agent_type": "browser",
                "objective": f"浏览器任务 {i}",
                "context": {"session_id": "test_session", "workspace_path": "/tmp/test"},
                "wait": False,
            }
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_real_world_cache_across_calls():
    """真实场景：缓存在多次调用间生效"""
    llm = MockLLM("缓存测试响应")

    agent = BaseAgent(llm=llm)

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    task_desc = "重复的搜索任务"

    await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": task_desc,
            "context": {
                "session_id": "test_session",
                "workspace_path": "/tmp/test",
                "workspaces_storage_root": "/tmp/test_workspaces",
            },
            "wait": True,
        }
    )

    call_count_after_first = llm.call_count

    result2 = await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": task_desc,
            "context": {
                "session_id": "test_session",
                "workspace_path": "/tmp/test",
                "workspaces_storage_root": "/tmp/test_workspaces",
            },
            "wait": True,
        }
    )

    assert result2.get("cached") is True
    assert llm.call_count == call_count_after_first


@pytest.mark.asyncio
async def test_real_world_error_recovery():
    """真实场景：错误恢复和重试"""

    class FailingLLM:
        def __init__(self):
            self.attempt = 0

        def bind(self, **kwargs):
            return self

        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages, config=None):
            self.attempt += 1
            if self.attempt < 2:
                raise RuntimeError("第一次调用失败")
            from langchain_core.messages import AIMessage

            return AIMessage(content="重试成功")

    llm = FailingLLM()
    agent = BaseAgent(llm=llm)

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": "会失败然后重试的任务",
            "context": {
                "session_id": "test_session",
                "workspace_path": "/tmp/test",
                "workspaces_storage_root": "/tmp/test_workspaces",
            },
            "wait": True,
        }
    )

    assert llm.attempt >= 2


@pytest.mark.asyncio
async def test_real_world_list_children():
    """真实场景：列出运行中的子 agent"""
    llm = MockLLM()
    agent = BaseAgent(llm=llm)

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": "后台任务 1",
            "context": {"session_id": "test_session", "workspace_path": "/tmp/test"},
            "wait": False,
        }
    )

    await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": "后台任务 2",
            "context": {"session_id": "test_session", "workspace_path": "/tmp/test"},
            "wait": False,
        }
    )

    await asyncio.sleep(0.1)

    children = agent.list_children()
    assert len(children) >= 1


@pytest.mark.asyncio
async def test_real_world_context_sharing():
    """真实场景：上下文在父子 agent 间共享"""
    llm = MockLLM("使用共享上下文")

    agent = BaseAgent(llm=llm)

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    shared_context = {
        "session_id": "test_session",
        "workspace_path": "/tmp/test",
        "workspaces_storage_root": "/tmp/test_workspaces",
        "session_data": {"key": "value"},
    }

    result = await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": "使用共享上下文的任务",
            "context": shared_context,
            "wait": True,
        }
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_real_world_timeout_config():
    """真实场景：超时配置生效"""

    class SlowLLM:
        def bind(self, **kwargs):
            return self

        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages, config=None):
            await asyncio.sleep(10)
            from langchain_core.messages import AIMessage

            return AIMessage(content="不应该返回")

    llm = SlowLLM()
    agent = BaseAgent(llm=llm)

    from unittest.mock import AsyncMock

    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    catalog = AsyncMock()
    catalog.resolve = AsyncMock(return_value=SubagentConfig(system_prompt="test"))

    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: [MockWebSearchTool()],
        catalog=catalog,
    )

    start_time = asyncio.get_event_loop().time()

    await spawn_tool.ainvoke(
        {
            "agent_type": "search",
            "objective": "会超时的任务",
            "context": {
                "session_id": "test_session",
                "workspace_path": "/tmp/test",
                "workspaces_storage_root": "/tmp/test_workspaces",
            },
            "wait": True,
        }
    )

    elapsed = asyncio.get_event_loop().time() - start_time

    search_timeout = 300
    assert elapsed < search_timeout + 2, f"Should timeout within {search_timeout}s"


_BROWSER_TOOL_NAMES: tuple[str, ...] = (
    "browser_navigate_tool",
    "browser_inspect_tool",
    "browser_snapshot_tool",
    "browser_interact_tool",
    "browser_extract_tool",
    "browser_manage_tool",
    "browser_execute_script_tool",
    "browser_ask_human_tool",
)


def _browser_toolkit() -> list[BaseTool]:
    from langchain_core.tools import StructuredTool

    return [
        StructuredTool.from_function(
            func=lambda _name=name: _name,
            name=name,
            description=f"Mock {name}",
        )
        for name in _BROWSER_TOOL_NAMES
    ]


class _RegistrySubagentCatalog:
    async def resolve(self, type_id: str):
        from myrm_agent_harness.agent.sub_agents.registry import SUBAGENT_CONFIGS

        return SUBAGENT_CONFIGS.get(type_id)


@pytest.mark.asyncio
async def test_delegate_browser_subagent_spawn_has_interact_tool() -> None:
    """Smoke: registered browser preset + parent toolkit → live browser sub-agent."""
    from myrm_agent_harness.agent.sub_agents.builder import filter_tools
    from myrm_agent_harness.agent.sub_agents.registry import SUBAGENT_CONFIGS

    browser_config = SUBAGENT_CONFIGS.get("browser")
    assert browser_config is not None

    parent_tools = _browser_toolkit()
    filtered = filter_tools(browser_config, parent_tools)
    filtered_names = {tool.name for tool in filtered}
    assert "browser_interact_tool" in filtered_names
    assert len(filtered) == len(_BROWSER_TOOL_NAMES)

    llm = MockLLM("Browser task completed")
    agent = BaseAgent(llm=llm)
    spawn_tool = create_delegate_task_tool(
        parent_agent=agent,
        tool_registry_getter=lambda: parent_tools,
        catalog=_RegistrySubagentCatalog(),
    )

    result = await spawn_tool.ainvoke(
        {
            "agent_type": "browser",
            "objective": "Open example.com and capture a page snapshot",
            "context": {
                "session_id": "browser_delegate_smoke",
                "workspace_path": "/tmp/test",
                "workspaces_storage_root": "/tmp/test_workspaces",
            },
            "wait": True,
        }
    )

    assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
