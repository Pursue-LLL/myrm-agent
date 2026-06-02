"""Server Global State Management

Provides access to globally shared instances that are initialized during application startup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler

logger = logging.getLogger(__name__)

_optimization_scheduler: OptimizationScheduler | None = None


def get_optimization_scheduler() -> OptimizationScheduler | None:
    """Get the global OptimizationScheduler instance

    Returns:
        OptimizationScheduler | None: The scheduler instance, or None if not initialized
    """
    return _optimization_scheduler


def set_optimization_scheduler(scheduler: OptimizationScheduler | None) -> None:
    """Set the global OptimizationScheduler instance

    Args:
        scheduler: The scheduler instance to set
    """
    global _optimization_scheduler
    _optimization_scheduler = scheduler
    if scheduler:
        logger.info("OptimizationScheduler instance registered")
    else:
        logger.warning("OptimizationScheduler instance cleared")


__all__ = ["get_optimization_scheduler", "set_optimization_scheduler"]
