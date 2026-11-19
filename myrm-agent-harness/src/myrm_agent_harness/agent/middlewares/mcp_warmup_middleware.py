"""MCP Warm-up Middleware.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, AgentState, ModelRequest, ModelResponse (POS: Middleware base and model-call types)
- langchain_core.messages::AIMessage (POS: Model response message carrying the tool calls)
- toolkits.mcp.warmup::McpWarmup (POS: Serves MCP tool tables from the local cache while the servers' sessions start)

[OUTPUT]
- McpWarmupMiddleware: Model-call wrapper that starts the MCP sessions behind cached tool tables as the first model
  request goes out and holds a response's tool calls until those sessions are up.

[POS]
Second half of the MCP tool-table cache. The Skill surface the model reads came from a cached table, so no session has
to be up before the model is asked: the sessions start while the request is in flight. A response that calls tools waits
here, inside the model node and so ahead of every ``after_model`` hook, because approval and the IPC policy gates read
the tool safety metadata that only a live session registers. A text answer never waits.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from myrm_agent_harness.toolkits.mcp.warmup import McpWarmup


def _calls_tools(response: ModelResponse[object]) -> bool:
    return any(isinstance(message, AIMessage) and message.tool_calls for message in response.result)


class McpWarmupMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Start the cached servers' sessions with the first model request; make tool calls wait for them."""

    def __init__(self, warmup: McpWarmup) -> None:
        super().__init__()
        self._warmup = warmup

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        self._warmup.start()
        response = await handler(request)
        if _calls_tools(response):
            await self._warmup.settle()
        return response
