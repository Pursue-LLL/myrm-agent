"""Thread sharing mode enumeration for topic-level session isolation.

[INPUT]
- (none)

[OUTPUT]
- ThreadSharingMode: Controls chat history visibility within a thread.

[POS]
Thread sharing mode enumeration for topic-level session isolation.
"""

from __future__ import annotations

from enum import StrEnum


class ThreadSharingMode(StrEnum):
    """Controls chat history visibility within a thread.

    - ISOLATED (default): Each user has their own conversation history.
    - SHARED: All users in the thread share the same conversation history,
      enabling collaborative scenarios (Discord Forum, Telegram Forum Topics).
    """

    ISOLATED = "isolated"
    SHARED = "shared"
