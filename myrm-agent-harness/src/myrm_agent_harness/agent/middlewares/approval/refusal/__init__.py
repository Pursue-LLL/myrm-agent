"""How an approval refusal reaches the model: which calls stay in the AI message and how the refusal reads.

[INPUT]
- .answer, .answered_calls, .wording

[OUTPUT]
- answered_call_ids, kept_tool_calls: which calls of a model response are answered and which stay in it
- refusal_answer, rejection_cause: the answer to a refused call, marked with who refused it
- DenialCause, denial_hint, rejection_message: who refused, and the wording the model reads

[POS]
The facade of the refusal domain. The approval middleware and its helpers import from here, never from a
submodule, so the parts can change without touching their callers.
"""

from .answer import refusal_answer, rejection_cause
from .answered_calls import answered_call_ids, kept_tool_calls
from .wording import DenialCause, denial_hint, rejection_message

__all__ = [
    "DenialCause",
    "answered_call_ids",
    "denial_hint",
    "kept_tool_calls",
    "refusal_answer",
    "rejection_cause",
    "rejection_message",
]
