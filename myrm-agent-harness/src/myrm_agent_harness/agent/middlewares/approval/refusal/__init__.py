"""How an approval refusal reaches the model: which calls stay in the AI message and how the refusal reads.

[INPUT]
- .answered_calls, .wording

[OUTPUT]
- answered_call_ids, kept_tool_calls: which calls of a model response are answered and which stay in it
- DenialCause, denial_hint, rejection_message: who refused, and the wording the model reads

[POS]
The facade of the refusal domain. The approval middleware and its helpers import from here, never from a
submodule, so the two halves can change without touching their callers.
"""

from .answered_calls import answered_call_ids, kept_tool_calls
from .wording import DenialCause, denial_hint, rejection_message

__all__ = ["DenialCause", "answered_call_ids", "denial_hint", "kept_tool_calls", "rejection_message"]
