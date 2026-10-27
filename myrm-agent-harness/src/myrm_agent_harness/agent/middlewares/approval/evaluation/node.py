"""The graph node that judges the tool calls of a model response before anyone is asked.

[INPUT]
- langchain.agents.middleware::AgentMiddleware (POS: The middleware base class; each hook it defines becomes one node of the agent graph.)
- .evaluator::evaluate_target, .record, .target

[OUTPUT]
- ApprovalEvaluationMiddleware: after_model hook that stores the evaluation of the latest model response in the graph state

[POS]
Registered right after ``ToolApprovalMiddleware`` in the middleware list, so the after_model hooks, which LangChain runs
from the last middleware to the first, reach it first. Its node commits its result to the checkpoint before the node
that may interrupt starts; resuming that node never runs this one again.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

from .evaluator import evaluate_target
from .record import APPROVAL_EVALUATION_KEY, ApprovalEvaluation, ApprovalEvaluationState
from .target import resolve_approval_target


class ApprovalEvaluationMiddleware(AgentMiddleware[ApprovalEvaluationState, None, object]):
    """Judge the calls of the latest model response and keep the verdicts for the approval node."""

    state_schema = ApprovalEvaluationState

    async def aafter_model(
        self, state: ApprovalEvaluationState, runtime: object
    ) -> dict[str, ApprovalEvaluation] | None:
        """Store the verdicts of the calls that still need one; nothing to store when there are none."""
        target = resolve_approval_target(state, runtime)
        if target is None:
            return None
        return {APPROVAL_EVALUATION_KEY: await evaluate_target(target)}
