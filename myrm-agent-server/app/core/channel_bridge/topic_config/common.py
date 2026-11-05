"""[INPUT]
- app.channels.types (POS: channel topic types)

[OUTPUT]
- Shared constants, the search-agent bind helpers and the logger.

[POS]
Shared primitives of the channel topic-config domain.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


_CACHE_TTL = 60.0


_CHANNEL_LEVEL_KEY = "__channel__"


_DEFAULT_IDLE_TIMEOUT_HOURS = 24


_ACTIVE_FLUSH_INTERVAL = 300.0


SEARCH_AGENT_CHANNEL_BIND_MSG = "Search agents cannot be bound to channels; choose a General agent."


_TOPIC_WORKSPACE_MUTUAL_EXCLUSIVE_MSG = "projectId and authorizedPath are mutually exclusive for topic workspace binding."


_UNSET: object = object()


def is_search_agent_channel_bind_error(exc: BaseException) -> bool:
    """Return True when bind_topic rejected a prompt_mode=search agent."""
    return isinstance(exc, ValueError) and str(exc) == SEARCH_AGENT_CHANNEL_BIND_MSG


def clean_identity_id(raw: str) -> str:
    """Sanitize an explicit team identity id at write time.

    Collapsing ids (empty or the reserved ``baseline`` default compartment)
    are rejected so two bindings can never silently share one memory
    compartment. Raises ValueError on rejection (fail-closed).
    """
    from myrm_agent_harness.agent.security.team_identity import sanitize_identity_id

    cleaned = sanitize_identity_id(raw)
    if not cleaned or cleaned == "baseline":
        raise ValueError(f"Invalid identity_id '{raw}'; use ASCII letters, digits, '-' or '_'.")
    return cleaned
