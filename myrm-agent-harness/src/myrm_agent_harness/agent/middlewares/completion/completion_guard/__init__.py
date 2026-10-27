"""Completion guard: the finish gate that holds an answer back until the run has earned it.

[INPUT]
- .guard::CompletionGuard, reset_completion_guard (POS: the after_model gate)
- .checklist::build_checklist (POS: task-aware verification checklist)
- .verification::classify_verification (POS: which bash command counts as verification)
- .safety::is_mutating_tool (POS: effectful tool detection)
- .state::attach_disclosure_to_event (POS: per-turn disclosure payload for the message_end event)

[OUTPUT]
- CompletionGuard, reset_completion_guard, build_checklist, classify_verification, is_mutating_tool, attach_disclosure_to_event

[POS]
Public surface of the completion guard package. The modules a caller outside the package needs besides these
(``capabilities``, ``directive_middleware``, ``state``) are imported by their own path.
"""

from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import build_checklist
from myrm_agent_harness.agent.middlewares.completion.completion_guard.guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.safety import is_mutating_tool
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import attach_disclosure_to_event
from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import classify_verification

__all__ = [
    "CompletionGuard",
    "attach_disclosure_to_event",
    "build_checklist",
    "classify_verification",
    "is_mutating_tool",
    "reset_completion_guard",
]
