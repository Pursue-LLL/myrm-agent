"""Pure time-interval checks for placeholder progress edits during execute_stream.

All clocks are `time.monotonic()`-compatible floats (seconds).

[INPUT]
- (none)

[OUTPUT]
- should_skip_throttled_placeholder_edit: Return True if a placeholder edit must wait (elapsed sinc...

[POS]
Pure time-interval checks for placeholder progress edits during execute_stream.
"""

from __future__ import annotations


def should_skip_throttled_placeholder_edit(now: float, last_edit_at: float, min_interval: float) -> bool:
    """Return True if a placeholder edit must wait (elapsed since last edit < min_interval).

    Callers pass `last_edit_at == 0.0` before the first edit in a stream so elapsed time is large
    for any realistic monotonic `now`, and the first edit is not blocked by `min_interval`.
    """
    return (now - last_edit_at) < min_interval
