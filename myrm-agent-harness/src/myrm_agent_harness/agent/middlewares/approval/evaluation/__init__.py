"""Judging a model response's tool calls once, ahead of the node that asks the person.

[INPUT]
- .evaluator, .node, .record, .target

[OUTPUT]
- ApprovalEvaluationMiddleware: the graph node that judges a batch and stores the verdicts
- ApprovalTarget, resolve_approval_target: the calls to judge and the session they are judged in
- evaluate_target: judge a target (the approval node does it itself when no verdicts were stored)
- APPROVAL_EVALUATION_KEY, ApprovalEvaluation, evaluation_matches, pending_calls, refused_calls: the stored verdicts

[POS]
The facade of the evaluation domain. ``ToolApprovalMiddleware`` imports from here, never from a submodule.
"""

from .evaluator import evaluate_target
from .node import ApprovalEvaluationMiddleware
from .record import (
    APPROVAL_EVALUATION_KEY,
    ApprovalEvaluation,
    evaluation_matches,
    pending_calls,
    refused_calls,
)
from .target import ApprovalTarget, resolve_approval_target

__all__ = [
    "APPROVAL_EVALUATION_KEY",
    "ApprovalEvaluation",
    "ApprovalEvaluationMiddleware",
    "ApprovalTarget",
    "evaluate_target",
    "evaluation_matches",
    "pending_calls",
    "refused_calls",
    "resolve_approval_target",
]
