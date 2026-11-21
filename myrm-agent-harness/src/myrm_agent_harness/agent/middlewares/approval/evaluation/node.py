"""The graph node that judges the tool calls of a model response before anyone is asked.

[INPUT]
- langchain.agents.middleware::AgentMiddleware (POS: The middleware base class; each hook it defines becomes one node of the agent graph.)
- .evaluator::evaluate_target, .pins::build_path_pins, .record, .target

[OUTPUT]
- ApprovalEvaluationMiddleware: after_model hook that stores the evaluation of the latest model response in the graph state, and the pins of its file calls

[POS]
Registered right after ``ToolApprovalMiddleware`` in the middleware list, so the after_model hooks, which LangChain runs
from the last middleware to the first, reach it first. Its node commits its result to the checkpoint before the node
that may interrupt starts; resuming that node never runs this one again. The pins are taken in the same node, before
any call of the response has run, so they name the files the verdicts are about.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

from .evaluator import evaluate_target
from .pins import build_path_pins
from .record import APPROVAL_EVALUATION_KEY, PATH_PINS_KEY, ApprovalEvaluation, ApprovalEvaluationState, PathPin
from .target import resolve_approval_target


class ApprovalEvaluationMiddleware(AgentMiddleware[ApprovalEvaluationState, None, object]):
    """Judge the calls of the latest model response and keep the verdicts for the approval node."""

    state_schema = ApprovalEvaluationState

    async def aafter_model(
        self, state: ApprovalEvaluationState, runtime: object
    ) -> dict[str, ApprovalEvaluation | dict[str, PathPin]] | None:
        """Store the verdicts of the calls that still need one and the pins of their file calls; nothing when there are none."""
        target = resolve_approval_target(state, runtime)
        if target is None:
            return None
        return {
            APPROVAL_EVALUATION_KEY: await evaluate_target(target),
            PATH_PINS_KEY: build_path_pins(target.unanswered.tool_calls, target.workspace_root),
        }
