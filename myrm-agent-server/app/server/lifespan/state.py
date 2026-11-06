"""[INPUT]
- app.services.chat.context_cleanup_scheduler::ContextCleanupScheduler (POS: context cleanup scheduler)

[OUTPUT]
- logger and the two mutable startup-state handles

[POS]
Process-wide startup state shared by the lifespan phases.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.runtime.context.cleanup_task import ContextCleanupScheduler

logger = logging.getLogger(__name__)


_checkpointer_cleanup: Callable[[], Awaitable[None]] | None = None


_context_cleanup_scheduler_instance: ContextCleanupScheduler | None = None
