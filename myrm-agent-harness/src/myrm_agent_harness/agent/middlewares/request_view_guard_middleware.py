"""Request View Guard Middleware.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, AgentState, ModelRequest, ModelResponse (POS: Middleware base and model-call types)
- agent.context_management.infra.cache_break_detector::get_cache_break_detector (POS: The run's prompt-cache break detector)
- agent.context_management.infra.prefix_chain::message_digests (POS: One digest per message, blind to cache breakpoints)

[OUTPUT]
- RequestViewGuardMiddleware: Innermost model-call wrapper that reports the message list the model is about to
  receive to the run's cache break detector, which finds where it stopped extending the previous request's.

[POS]
Last stop of a request before the provider: every other middleware has finished rewriting it, so the view it sees
is the view that is billed, cached and replayed.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse

from myrm_agent_harness.agent.context_management.infra.cache_break_detector import get_cache_break_detector
from myrm_agent_harness.agent.context_management.infra.prefix_chain import message_digests


class RequestViewGuardMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Record each request's message prefix on the run's cache break detector.

    The record is the only thing it does: the request goes on unchanged. Outside an agent run (no detector) the
    call is simply passed on.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        detector = get_cache_break_detector()
        if detector is not None:
            detector.record_message_prefix(message_digests(request.messages))
        return await handler(request)
