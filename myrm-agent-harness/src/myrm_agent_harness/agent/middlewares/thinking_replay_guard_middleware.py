"""Thinking Replay Guard Middleware.

[INPUT]
- langchain.agents.middleware::AgentMiddleware, AgentState, ModelRequest, ModelResponse (POS: Middleware base and model-call types)
- agent.middlewares._run_notices::run_scope (POS: The per-run dict a request carries)
- core.thinking_blocks::THINKING_BLOCKS_KEY, without_thinking_blocks (POS: The signed reasoning blocks an Anthropic-family answer carries)
- toolkits.llms.errors.classifier::classify_failover_reason (POS: Names the provider's refusal of a signed block)

[OUTPUT]
- ThinkingReplayGuardMiddleware: Model-call wrapper that answers a provider's refusal of replayed reasoning by sending the
  request once more without it, and keeps that choice for the rest of the run.

[POS]
Safety net of the signed-reasoning replay, one layer outside ``RequestViewGuardMiddleware``. The provider checks every
replayed block against the exact prompt it was written under; when something this stack cannot foresee (a model
switched by a failover, a prompt the provider changed) makes it refuse one, the request is sent again with every block
removed, which is always valid. Blocks are never put back within the run, because a block the provider has not seen
again would break the chain of those written without it.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares._run_notices import run_scope
from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY, without_thinking_blocks
from myrm_agent_harness.toolkits.llms.errors.classifier import classify_failover_reason
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# Key in the run dict: the provider refused replayed reasoning once, so this run replays none.
_REPLAY_REFUSED_KEY = "thinking_replay_refused"


def _carries_signed_reasoning(request: ModelRequest[None]) -> bool:
    return any(isinstance(m, AIMessage) and THINKING_BLOCKS_KEY in m.additional_kwargs for m in request.messages)


def _without_signed_reasoning(request: ModelRequest[None]) -> ModelRequest[None]:
    return request.override(messages=without_thinking_blocks(request.messages))


class ThinkingReplayGuardMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Retry a refused request once without its signed reasoning, and replay none for the rest of the run."""

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[object]]],
    ) -> ModelResponse[object]:
        scope = run_scope(request)
        if scope is not None and scope.get(_REPLAY_REFUSED_KEY):
            request = _without_signed_reasoning(request)
        try:
            return await handler(request)
        except Exception as exc:
            if (
                not _carries_signed_reasoning(request)
                or classify_failover_reason(exc) != FailoverReason.THINKING_SIGNATURE
            ):
                raise
            logger.warning("[ThinkingReplay] the provider refused replayed reasoning; retrying without it: %s", exc)
            if scope is not None:
                scope[_REPLAY_REFUSED_KEY] = True
            return await handler(_without_signed_reasoning(request))
