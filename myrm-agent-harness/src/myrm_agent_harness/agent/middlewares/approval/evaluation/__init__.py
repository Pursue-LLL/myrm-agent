"""Judging a model response's tool calls once, ahead of the node that asks the person.

[INPUT]
- .evaluator, .node, .pins, .record, .target

[OUTPUT]
- ApprovalEvaluationMiddleware: the graph node that judges a batch and stores the verdicts and the pins of its file calls
- ApprovalTarget, resolve_approval_target: the calls to judge and the session they are judged in
- evaluate_target: judge a target (the approval node does it itself when no verdicts were stored)
- APPROVAL_EVALUATION_KEY, ApprovalEvaluation, evaluation_matches, pending_calls, refused_calls: the stored verdicts
- path_moved, pin_of: the files each file call was judged on, and the check that a call still opens them

[POS]
The facade of the evaluation domain. ``ToolApprovalMiddleware`` and the path pin guard import from here, never from a
submodule.
"""

from .evaluator import evaluate_target
from .node import ApprovalEvaluationMiddleware
from .pins import path_moved, pin_of
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
    "path_moved",
    "pending_calls",
    "pin_of",
    "refused_calls",
    "resolve_approval_target",
]
