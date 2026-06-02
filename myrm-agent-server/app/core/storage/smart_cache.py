"""Smart Cached Storage — business-layer wrapper.

Re-exports the framework-level CachedStorageProvider with backward-compatible
class name. Since the framework version uses ``namespace`` instead of
``sandbox_id``, callers should migrate to the new parameter name.

[INPUT]
- myrm_agent_harness.toolkits.storage.cached (framework)

[OUTPUT]
- CacheStats, SmartCachedStorage: re-exported from framework

[POS]
Business-layer thin wrapper. Core caching logic lives in the framework.
"""

from myrm_agent_harness.toolkits.storage.cached import (
    CachedStorageProvider as SmartCachedStorage,
)
from myrm_agent_harness.toolkits.storage.cached import (
    CacheStats,
)

__all__ = ["CacheStats", "SmartCachedStorage"]
