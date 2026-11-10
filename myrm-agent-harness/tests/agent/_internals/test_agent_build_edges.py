"""The helpers an agent build is made of: the todo loader of the progress middleware, schema weaving, middleware tools."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable

import pytest
from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.agent._internals._agent_build import (
    _weave_dynamic_schemas,
    build_middlewares,
    build_tools,
    create_registry,
)
from myrm_agent_harness.agent.meta_tools.progress import storage as todo_storage
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore
from myrm_agent_harness.agent.tool_management import ToolRegistry, ToolSource

TodoLoader = Callable[[str | None], Awaitable[TodoStore | None]]

# The package re-exports a function under the module's name, so the module is imported by its path.
progress_module = importlib.import_module("myrm_agent_harness.agent.middlewares.progress_middleware")


def _todo_loader_of(monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> TodoLoader:
    """The loader ``build_middlewares`` hands to the progress middleware, caught on its way."""
    caught: list[TodoLoader] = []
    real = progress_module.progress_middleware

    def spy(get_todos_fn: TodoLoader) -> object:
        caught.append(get_todos_fn)
        return real(get_todos_fn)

    monkeypatch.setattr(progress_module, "progress_middleware", spy)
    build_middlewares(registry, [])
    return caught[0]


def _registry_with_todo_write() -> ToolRegistry:
    @tool("todo_write")
    def todo_write(items: str) -> str:
        """Write the todo list."""
        return items

    registry = create_registry()
    registry.register(todo_write, source=ToolSource.USER)
    return registry


class _TodoReads:
    """Stands in for the workspace todo reader and records which workspace roots it was asked for."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, fail_with: OSError | None = None) -> None:
        self.roots: list[str] = []
        self.store = TodoStore(todos=[])
        self._fail_with = fail_with
        monkeypatch.setattr(todo_storage, "read_todos_sync_from_workspace", self)

    def __call__(self, workspace_root: str) -> TodoStore:
        self.roots.append(workspace_root)
        if self._fail_with is not None:
            raise self._fail_with
        return self.store


class TestTodoLoader:
    async def test_a_run_without_a_workspace_has_no_todos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reads = _TodoReads(monkeypatch)
        load = _todo_loader_of(monkeypatch, _registry_with_todo_write())

        assert await load(None) is None
        assert await load("") is None
        assert reads.roots == []

    async def test_a_run_that_cannot_update_todos_never_reads_them(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reads = _TodoReads(monkeypatch)
        load = _todo_loader_of(monkeypatch, create_registry())

        assert await load("/workspace") is None
        assert reads.roots == []

    async def test_a_run_that_keeps_a_todo_list_reads_the_workspace_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = _TodoReads(monkeypatch)
        load = _todo_loader_of(monkeypatch, _registry_with_todo_write())

        assert await load("/workspace") is reads.store
        assert reads.roots == ["/workspace"]

    async def test_an_unreadable_store_means_no_todos_and_a_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        reads = _TodoReads(monkeypatch, fail_with=OSError("disk gone"))
        load = _todo_loader_of(monkeypatch, _registry_with_todo_write())

        with caplog.at_level(logging.WARNING):
            assert await load("/workspace") is None

        assert reads.roots == ["/workspace"]
        assert "disk gone" in caplog.text


class _HintedTool(BaseTool):
    """A tool whose description follows the tools the agent holds."""

    name: str = "hinted_tool"
    description: str = "Plain description."

    def _run(self, *args: object, **kwargs: object) -> str:
        return ""

    def dynamic_schema_modifier(self, available_names: set[str]) -> BaseTool:
        suffix = "with search" if "web_search_tool" in available_names else "without search"
        return self.model_copy(update={"description": f"Hinted {suffix}."})


class _BrokenHintTool(_HintedTool):
    name: str = "broken_hint_tool"

    def dynamic_schema_modifier(self, available_names: set[str]) -> BaseTool:
        raise RuntimeError("modifier exploded")


class TestSchemaWeaving:
    def test_a_tool_sees_the_names_of_the_tools_it_is_bound_with(self) -> None:
        @tool("web_search_tool")
        def web_search_tool(query: str) -> str:
            """Search the web."""
            return query

        with_search = _weave_dynamic_schemas([_HintedTool(), web_search_tool])
        without_search = _weave_dynamic_schemas([_HintedTool()])

        assert with_search[0].description == "Hinted with search."
        assert without_search[0].description == "Hinted without search."
        assert with_search[1] is web_search_tool

    def test_a_failing_modifier_leaves_the_original_schema_and_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        broken = _BrokenHintTool()

        with caplog.at_level(logging.WARNING):
            woven = _weave_dynamic_schemas([broken])

        assert woven == [broken]
        assert "modifier exploded" in caplog.text


class _ToolProvider:
    """A middleware that exposes tools."""

    def __init__(self, *tools: BaseTool) -> None:
        self._tools = list(tools)

    def get_tools(self) -> list[BaseTool]:
        return self._tools


class _BrokenToolProvider:
    def get_tools(self) -> list[BaseTool]:
        raise RuntimeError("provider exploded")


class TestMiddlewareTools:
    async def test_tools_a_middleware_exposes_join_the_registry_and_internal_ones_stay_out_of_the_schema(self) -> None:
        @tool("visible_tool")
        def visible_tool(text: str) -> str:
            """A tool the model sees."""
            return text

        @tool("_internal_tool")
        def internal_tool(text: str) -> str:
            """A tool only a middleware may call."""
            return text

        registry = create_registry()
        bound = await build_tools(registry, [], [_ToolProvider(visible_tool, internal_tool), _ToolProvider()])

        assert [t.name for t in bound] == ["visible_tool"]
        assert [t.name for t in registry.get_runtime_tools()] == ["_internal_tool"]

    async def test_a_middleware_whose_tools_cannot_be_read_is_skipped_with_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @tool("visible_tool")
        def visible_tool(text: str) -> str:
            """A tool the model sees."""
            return text

        with caplog.at_level(logging.WARNING):
            bound = await build_tools(create_registry(), [], [_BrokenToolProvider(), _ToolProvider(visible_tool)])

        assert [t.name for t in bound] == ["visible_tool"]
        assert "provider exploded" in caplog.text
