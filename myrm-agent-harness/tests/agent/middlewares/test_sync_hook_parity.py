"""Sync wrap hooks for middlewares that define only the async variant (signoff clarify pool warm).

LangChain puts a middleware in the sync tool and model chains as soon as its class defines either variant of a wrap
hook, and the default sync variant raises. ``apply_sync_hook_parity`` fills the missing sync variant with a
pass-through and must change nothing else about the middleware: its other hooks decide which graph nodes exist.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from myrm_agent_harness.agent.middlewares.sync_hook_parity import apply_sync_hook_parity


class _AsyncModelHook(AgentMiddleware):  # type: ignore[type-arg]
    """Defines the async model hook, a before_model hook and an attribute; nothing sync to wrap with."""

    marker = "kept"

    def before_model(self, state: dict[str, Any], runtime: object) -> dict[str, Any] | None:
        return None

    async def awrap_model_call(
        self,
        request: ModelRequest[object],
        handler: Callable[[ModelRequest[object]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        return await handler(request)


class _AsyncToolHook(AgentMiddleware):  # type: ignore[type-arg]
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def awrap_tool_call(
        self, request: object, handler: Callable[[object], Awaitable[ToolMessage]]
    ) -> ToolMessage:
        self.seen.append("async")
        return await handler(request)


class _BothVariants(AgentMiddleware):  # type: ignore[type-arg]
    def wrap_model_call(self, request: object, handler: Callable[[object], object]) -> object:
        return handler(request)

    async def awrap_model_call(self, request: object, handler: Callable[[object], Awaitable[object]]) -> object:
        return await handler(request)


class _SyncOnly(AgentMiddleware):  # type: ignore[type-arg]
    def wrap_tool_call(self, request: object, handler: Callable[[object], object]) -> object:
        return handler(request)


class _NoWrapHooks(AgentMiddleware):  # type: ignore[type-arg]
    def after_model(self, state: dict[str, Any], runtime: object) -> dict[str, Any] | None:
        return None


class _Scripted(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> _Scripted:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        called = any(isinstance(m, ToolMessage) for m in messages)
        reply = (
            AIMessage(content="done")
            if called
            else AIMessage(content="", tool_calls=[{"id": "c1", "name": "ping", "args": {}}])
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


@tool
def ping() -> str:
    """Answer pong."""
    return "pong"


def test_a_middleware_with_only_an_async_model_hook_gets_a_sync_pass_through() -> None:
    middleware = _AsyncModelHook()
    seen: list[object] = []
    request = MagicMock()

    apply_sync_hook_parity([middleware])
    result = middleware.wrap_model_call(request, lambda r: seen.append(r) or "response")  # type: ignore[arg-type, return-value]

    assert result == "response"
    assert seen == [request]


def test_a_middleware_with_only_an_async_tool_hook_gets_a_sync_pass_through() -> None:
    middleware = _AsyncToolHook()

    apply_sync_hook_parity([middleware])

    assert middleware.wrap_tool_call(MagicMock(), lambda r: "tool-result") == "tool-result"  # type: ignore[arg-type, return-value]


def test_the_middleware_stays_the_same_object_with_everything_it_defined() -> None:
    middleware = _AsyncModelHook()

    [adapted] = apply_sync_hook_parity([middleware])

    assert adapted is middleware
    assert isinstance(adapted, _AsyncModelHook)
    assert type(adapted).__name__ == "_AsyncModelHook"
    assert adapted.name == "_AsyncModelHook"
    assert adapted.marker == "kept"
    assert type(adapted).before_model is _AsyncModelHook.before_model
    assert type(adapted).awrap_model_call is _AsyncModelHook.awrap_model_call


@pytest.mark.parametrize("middleware", [_BothVariants(), _SyncOnly(), _NoWrapHooks(), AgentMiddleware()])
def test_a_middleware_that_needs_no_pass_through_keeps_its_class(middleware: AgentMiddleware) -> None:  # type: ignore[type-arg]
    cls = type(middleware)

    apply_sync_hook_parity([middleware])

    assert type(middleware) is cls


def test_a_second_pass_changes_nothing_and_instances_of_a_class_share_one_subclass() -> None:
    first, second = _AsyncModelHook(), _AsyncModelHook()

    apply_sync_hook_parity([first, second])
    after_first_pass = type(first)
    apply_sync_hook_parity([first])

    assert type(first) is after_first_pass
    assert type(second) is after_first_pass


def test_objects_that_are_not_middlewares_pass_through_untouched() -> None:
    plain = object()

    assert apply_sync_hook_parity([plain]) == [plain]


def test_the_parity_pass_leaves_the_graph_nodes_of_the_middleware_as_they_were() -> None:
    plain = create_agent(_Scripted(), tools=[ping], middleware=[_AsyncModelHook()])
    adapted = create_agent(_Scripted(), tools=[ping], middleware=apply_sync_hook_parity([_AsyncModelHook()]))  # type: ignore[arg-type]

    assert set(adapted.get_graph().nodes) == set(plain.get_graph().nodes)
    assert "_AsyncModelHook.before_model" in adapted.get_graph().nodes


def test_a_sync_run_passes_through_a_middleware_that_has_only_async_wrap_hooks() -> None:
    tool_hook = _AsyncToolHook()
    agent = create_agent(
        _Scripted(),
        tools=[ping],
        middleware=apply_sync_hook_parity([_AsyncModelHook(), tool_hook]),  # type: ignore[arg-type]
    )

    result = agent.invoke({"messages": [HumanMessage(content="ping it")]})

    assert result["messages"][-1].content == "done"
    assert tool_hook.seen == []
