"""Model Call Cancel Middleware.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, ModelRequest, ModelResponse (POS: Middleware base and model-call types)
- utils.runtime.cancellation::run_until_cancelled (POS: Races an awaitable against the run's cancel token)

[OUTPUT]
- ModelCallCancelMiddleware: Outermost model-call wrapper. A Stop that lands while a model request is still in flight
  (before its first token, or inside a provider retry or backoff wait) aborts the request within one poll interval and
  raises ``OperationCancelledError`` for the stream executor, instead of waiting for the next stream chunk to look at
  the token.

[POS]
Run-lifecycle guarantee of the agent chain: cancellation reaches the model leg of a turn the way the tool gate reaches
the tool leg.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from myrm_agent_harness.utils.runtime.cancellation import run_until_cancelled


class ModelCallCancelMiddleware(AgentMiddleware[Any, Any]):
    """Abort an in-flight model request as soon as the run's cancel token fires.

    The executor only reads the token when a stream chunk arrives, so a request that is silent (long prefill, hidden
    reasoning, a rate-limit sleep) would otherwise keep the turn, its session and its gateway slot busy until the
    provider answers. One race per model call; outside an agent run (no token) the call is simply awaited.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await run_until_cancelled(handler(request))
