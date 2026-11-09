"""Integration test for the parallel tool-calls switch.

``ParallelToolCallsMiddleware``: the engine's switch reaches the model's tool binding of a real
``TransportChatModel``.

How the calls of one turn share or exclude each other is pinned in ``test_tool_conflict_gate`` and, on the graph a
run builds, in ``test_shipped_stack_tool_dispatch``.
"""

from __future__ import annotations

import pytest


class TestParallelToolCallsReachTransportChatModel:
    """The setting the middleware puts on a model request is what ``TransportChatModel.bind_tools`` binds."""

    @staticmethod
    async def _bound(parallel: bool, model_settings: dict[str, object] | None = None):
        from langchain.agents.middleware import ModelRequest, ModelResponse
        from langchain_core.messages import AIMessage
        from langchain_core.tools import tool

        from myrm_agent_harness.agent.middlewares.parallel_tool_calls import ParallelToolCallsMiddleware
        from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel

        @tool
        def probe() -> str:
            """A test tool."""
            return "ok"

        bound = []

        async def handler(request: ModelRequest) -> ModelResponse:
            # What langchain's agent factory does with the request it is handed.
            bound.append(
                request.model.bind_tools(request.tools, tool_choice=request.tool_choice, **request.model_settings)
            )
            return ModelResponse(result=[AIMessage(content="")])

        request = ModelRequest(
            model=TransportChatModel(model="test-model", api_key="test-key"),
            messages=[],
            tools=[probe],
            model_settings=model_settings,
        )
        await ParallelToolCallsMiddleware(parallel).awrap_model_call(request, handler)
        return bound[0]

    @pytest.mark.parametrize("parallel", [True, False])
    async def test_the_setting_is_bound_to_the_model(self, parallel: bool) -> None:
        bound = await self._bound(parallel)

        assert bound.kwargs.get("parallel_tool_calls") is parallel

    async def test_a_setting_the_request_carries_is_not_overridden(self) -> None:
        bound = await self._bound(True, {"parallel_tool_calls": False})

        assert bound.kwargs.get("parallel_tool_calls") is False
