"""Channel topic configuration.

[INPUT]
- .manager (POS: SqlTopicManager)

[OUTPUT]
- SqlTopicManager, the channel key constant and the bind-error helpers.

[POS]
Aggregate exit of the topic-config package.
"""

from __future__ import annotations

from .common import (
    _CHANNEL_LEVEL_KEY,
    _TOPIC_WORKSPACE_MUTUAL_EXCLUSIVE_MSG,
    SEARCH_AGENT_CHANNEL_BIND_MSG,
    clean_identity_id,
    is_search_agent_channel_bind_error,
)
from .manager import SqlTopicManager

__all__ = [
    "SqlTopicManager",
    "_CHANNEL_LEVEL_KEY",
    "SEARCH_AGENT_CHANNEL_BIND_MSG",
    "_TOPIC_WORKSPACE_MUTUAL_EXCLUSIVE_MSG",
    "clean_identity_id",
    "is_search_agent_channel_bind_error",
]
