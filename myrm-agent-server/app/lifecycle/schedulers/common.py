"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- logger, _MONITOR_CLEANUP_BATCH_SIZE, _MONITOR_STARTUP_MAX_BATCHES

[POS]
Lifecycle schedulers: shared logger and monitor constants.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


_MONITOR_CLEANUP_BATCH_SIZE = 500


_MONITOR_STARTUP_MAX_BATCHES = 4
