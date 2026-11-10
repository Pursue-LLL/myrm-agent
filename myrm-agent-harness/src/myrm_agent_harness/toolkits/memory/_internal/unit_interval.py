"""Range check for the 0.0-1.0 scores a caller sets on a memory.

[INPUT]
- memory._internal.storage::MemoryRejectedError (POS: refusal whose message is addressed to the caller and shown as written.)

[OUTPUT]
- require_unit_interval: refuse a score outside 0.0-1.0 with a message the caller can act on

[POS]
The one range check for every entrance that takes an importance or confidence score (updating a memory, saving
knowledge through the agent tool or the MCP tool), so each refuses a bad score in the same words and before anything
is buffered, queued or written.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory._internal.storage import MemoryRejectedError


def require_unit_interval(name: str, value: float | None, *, action: Literal["saved", "updated"]) -> None:
    """Refuse a score outside 0.0-1.0, which the memory models cannot read back once it is stored.

    ``None`` means the caller did not set the score and always passes; NaN fails the comparison and is refused.
    """
    if value is not None and not 0.0 <= value <= 1.0:
        raise MemoryRejectedError(
            f"Not {action}: {name} must be between 0.0 and 1.0 (got {value}). Retry with a value in that range."
        )
