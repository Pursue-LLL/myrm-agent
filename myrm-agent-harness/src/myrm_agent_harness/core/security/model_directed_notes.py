"""Where a refusal result stops being written for a person and starts being written for the model.

[INPUT]
- (none — pure text)

[OUTPUT]
- SYSTEM_NOTE_OPEN: the opening of a ``[System: ...]`` note addressed to the model
- DIAGNOSTIC_OPEN: the opening of the ``[SECURITY_DENIAL_DIAGNOSTIC]`` block addressed to the model
- user_facing_text: a refusal result without the notes that instruct the model

[POS]
A refused tool call is answered by one ToolMessage that the model and the person watching the run both read. Its
first line says what was refused and why. The notes after it tell the model how to proceed, in the model's
vocabulary, and mean nothing to a person. The producers open a note with these constants and a consumer that
shows the result to a person cuts at them, so the two cannot drift apart.
"""

from __future__ import annotations

SYSTEM_NOTE_OPEN = "[System: "
DIAGNOSTIC_OPEN = "[SECURITY_DENIAL_DIAGNOSTIC]"

_BLOCK_STARTS = tuple(f"\n\n{opening}" for opening in (SYSTEM_NOTE_OPEN, DIAGNOSTIC_OPEN))


def user_facing_text(content: str) -> str:
    """*content* up to the first note addressed to the model; empty when it opens with one."""
    cuts = [at for start in _BLOCK_STARTS if (at := content.find(start)) != -1]
    return content[: min(cuts)] if cuts else content
