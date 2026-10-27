"""Rules of the scheduled remote memory backup: the interval, when a backup is due, when the user is told.

[INPUT]
app.services.memory.backup.remote_sync.state::RemoteSyncState (POS: recorded outcome of the scheduled runs)

[OUTPUT]
- interval_minutes: the interval the user chose, clamped into the supported range
- is_due: whether the interval has passed since the last recorded success
- should_alert: whether a failure streak deserves a notification
- TICK_MINUTES / MIN_INTERVAL_MINUTES / MAX_INTERVAL_MINUTES / DEFAULT_INTERVAL_MINUTES / ALERT_AFTER_FAILURES

[POS]
Pure functions over an explicit clock: no I/O, no scheduler. Only a recorded success moves the schedule, so a failed
attempt is retried at the next tick, while a restart never repeats a backup that is not due. A success dated in the
future (a clock that ran ahead and was corrected) proves nothing and never holds a backup back.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.memory.backup.remote_sync.state import RemoteSyncState

TICK_MINUTES = 60  # how often the scheduler asks whether a backup is due
MIN_INTERVAL_MINUTES = TICK_MINUTES  # a shorter interval could not be honoured: the next tick would be later than it
MAX_INTERVAL_MINUTES = 1440
DEFAULT_INTERVAL_MINUTES = 1440
ALERT_AFTER_FAILURES = 2

# Ticks drift by seconds; without this a backup due "at the 24th hour" would wait for the tick after it.
_TICK_JITTER = timedelta(minutes=5)
# A failure streak is a short outage, not a lost safety net, while the last success is younger than this many intervals.
_OUTAGE_INTERVALS = 2


def interval_minutes(raw: object) -> int:
    """The stored ``syncInterval``; anything that is not a whole number falls back to the default."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return DEFAULT_INTERVAL_MINUTES
    return min(max(raw, MIN_INTERVAL_MINUTES), MAX_INTERVAL_MINUTES)


def is_due(state: RemoteSyncState, interval: int, now: datetime) -> bool:
    last = state.last_success_at
    if last is None or last > now:
        return True
    return now - last >= timedelta(minutes=interval) - _TICK_JITTER


def should_alert(state: RemoteSyncState, interval: int, now: datetime) -> bool:
    """True once per failure streak, when the failures repeat and no recent success still protects the memories."""
    if state.alerted or state.consecutive_failures < ALERT_AFTER_FAILURES:
        return False
    last = state.last_success_at
    if last is None or last > now:
        return True
    return now - last > _OUTAGE_INTERVALS * timedelta(minutes=interval)
