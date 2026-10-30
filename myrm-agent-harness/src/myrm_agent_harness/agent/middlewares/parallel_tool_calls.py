"""Parallel Tool Calls Middleware.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, AgentState, ModelRequest, ModelResponse (POS: Middleware base and model-call types; ``ModelRequest.model_settings`` is the public way to pass keyword arguments to ``bind_tools``)

[OUTPUT]
- ParallelToolCallsMiddleware: tells the provider, on every model call that offers tools, whether the model may answer with several tool calls in one turn

[POS]
Engine switch ``EngineParams.enable_parallel_tool_calls``. The setting rides on the model request, so the same
graph, a failover rebuild included, applies it to whichever model it runs, and nothing in the model object is replaced.
A model call that offers no tools gets no setting: providers reject ``parallel_tool_calls`` without tools. A setting the
request already carries is kept.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse


class ParallelToolCallsMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Send ``parallel_tool_calls`` with every model call that offers tools.

    It sits behind the middlewares that rewrite the tool list, so "offers tools" is judged on the list the model is
    bound to.
    """

    def __init__(self, parallel: bool) -> None:
        super().__init__()
        self._parallel = parallel

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        if not request.tools:
            return await handler(request)
        settings = {"parallel_tool_calls": self._parallel, **request.model_settings}
        return await handler(request.override(model_settings=settings))
