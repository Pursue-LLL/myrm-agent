"""Thread sharing setting of a topic binding.

[INPUT]
- (none)

[OUTPUT]
- ThreadSharingMode: the per-topic thread sharing value that is stored and returned by the topic API

[POS]
Value type of the per-topic ``thread_sharing_mode`` setting. Session keys do not read it: the members of a
group thread share one conversation whichever value is set.
"""

from __future__ import annotations

from enum import StrEnum


class ThreadSharingMode(StrEnum):
    """The per-topic thread sharing setting: ``isolated`` (default) or ``shared``.

    Stored with the topic binding and returned by the topic API. The session key builder does not read it, so
    both values give the same conversation scope: the members of a group or thread share one conversation and
    each DM sender has their own.
    """

    ISOLATED = "isolated"
    SHARED = "shared"
