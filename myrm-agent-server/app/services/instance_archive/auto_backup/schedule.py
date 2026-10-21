"""When a scheduled backup is due, and when the user should be told it is not happening.

[INPUT]
- app.services.instance_archive.auto_backup.models (POS: settings, state)

[OUTPUT]
- reference_moment: the moment due and overdue are measured from
- is_due: should the hourly tick start a backup now
- is_overdue: enabled, but no backup for far longer than the chosen frequency
- ALERT_AFTER_FAILURES: consecutive failures after which the user is notified once

[POS]
Pure rules, no I/O and no clock of their own. Due-ness is measured from the reference
moment: the newest backup that exists in the destination folder (the caller dates it
no later than ``now``), so a run missed while the app was closed is made up at the next
tick, and a folder that was emptied or never held a backup is due at once. A folder
that cannot be read is unknown rather than empty: the last successful attempt stands
in for it, so unplugging a drive does not read as a missing backup. A failed
attempt is retried at the following ticks, then backs off to the chosen frequency
so a permanently broken destination is not hammered. A moment dated after ``now`` comes
from a clock that ran ahead and was corrected: it proves nothing, so an attempt dated
that way neither stands in for an unreadable folder nor holds a retry back.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.instance_archive.auto_backup.models import AutoBackupSettings, AutoBackupState

ALERT_AFTER_FAILURES = 2
_QUICK_RETRY_GAP = timedelta(minutes=30)
_QUICK_RETRIES = 3
_OVERDUE_INTERVALS = 2


def _attempt_so_far(state: AutoBackupState, now: datetime) -> datetime | None:
    """The last attempt, unless it is dated after ``now``: a clock that ran ahead stamped it, and waiting for the
    clock to catch up with it would stop the schedule for as long as the clock was off."""
    attempt = state.last_attempt_at
    return attempt if attempt is not None and attempt <= now else None


def reference_moment(last_backup_at: datetime | None, reachable: bool, state: AutoBackupState, now: datetime) -> datetime | None:
    """The moment due and overdue are measured from: the folder's newest backup, or when the folder cannot be read
    and the last attempt succeeded, that attempt. After a failure nothing stands in and the retry back-off applies."""
    if reachable:
        return last_backup_at
    return _attempt_so_far(state, now) if state.consecutive_failures == 0 else None


def is_due(settings: AutoBackupSettings, state: AutoBackupState, reference: datetime | None, now: datetime) -> bool:
    if not settings.enabled:
        return False
    interval = settings.frequency.interval
    attempt = _attempt_so_far(state, now)
    if state.consecutive_failures > 0 and attempt is not None:
        wait = interval if state.consecutive_failures >= _QUICK_RETRIES else _QUICK_RETRY_GAP
        if now - attempt < wait:
            return False
    return reference is None or now - reference >= interval


def is_overdue(settings: AutoBackupSettings, state: AutoBackupState, reference: datetime | None, now: datetime) -> bool:
    if not settings.enabled:
        return False
    if reference is None:
        return state.consecutive_failures > 0
    return now - reference > settings.frequency.interval * _OVERDUE_INTERVALS
