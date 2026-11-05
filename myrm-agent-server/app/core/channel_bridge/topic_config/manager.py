"""[INPUT]
- .binding / .identity / .policy / .config_store (POS: the four mixins)

[OUTPUT]
- SqlTopicManager

[POS]
The topic manager: one class composed from the binding, identity, policy and config-store mixins.
"""

from __future__ import annotations

from .binding import BindingMixin
from .common import _DEFAULT_IDLE_TIMEOUT_HOURS
from .config_store import ConfigStoreMixin
from .identity import IdentityMixin
from .policy import PolicyMixin


class SqlTopicManager(BindingMixin, IdentityMixin, PolicyMixin, ConfigStoreMixin):
    """Manages per-topic/channel configuration in UserConfig DB.

    Config structure in UserConfig (config_key = "telegramTopics" etc.):
    {
        "<chat_id>": {
            "<thread_id>": {
                "agentId": "uuid-of-agent",
                "projectId": "uuid-of-project",
                "authorizedPath": "/path/to/vault",
                "enabled": true,
                "boundAt": "2026-03-06T12:00:00Z",
                "lastActiveAt": "2026-03-30T12:00:00Z",
                "idleTimeoutH": 24,
                "maxAgeH": null
            },
            "__channel__": { ... }
        }
    }"""

    def __init__(
        self,
        idle_timeout_hours: int = _DEFAULT_IDLE_TIMEOUT_HOURS,
        max_age_hours: int | None = None,
    ) -> None:
        self._cache: dict[str, dict[str, object]] = {}
        self._cache_ts: dict[str, float] = {}
        self._default_idle_timeout_h = idle_timeout_hours
        self._default_max_age_h = max_age_hours
        self._active_mem: dict[str, str] = {}
        self._active_flush_ts: dict[str, float] = {}
