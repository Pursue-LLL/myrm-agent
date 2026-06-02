"""Skill Metrics Provider - Evolution System Integration

Connects skill_optimization system to evolution system for funnel metrics.
Provides SkillMetrics (total_selections, applied_count, completed_count, success_count)
from the evolution store to enable funnel analysis in the Optimization Dashboard.

Architecture:
- Business layer implementation of SkillMetricsProvider protocol
- Read-only access to evolution system's SkillStore
- Single source of truth: metrics only stored in evolution system
- Optional integration: optimization system works without this provider

Usage:
    from myrm_agent_harness.agent.skills.evolution import SkillStore
    from .metrics_provider import EvolutionMetricsProvider

    evolution_store = SkillStore()
    provider = EvolutionMetricsProvider(evolution_store)

    # Pass to optimization system
    scheduler = OptimizationScheduler(..., metrics_provider=provider)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.evolution import SkillStore
    from myrm_agent_harness.agent.skills.evolution.core.types import SkillMetrics

logger = logging.getLogger(__name__)


class EvolutionMetricsProvider:
    """Evolution System Metrics Provider

    Implements SkillMetricsProvider protocol by reading from evolution SkillStore.
    Provides funnel metrics (selections, applications, completions, successes)
    to enable detailed diagnostic analysis in Optimization Dashboard.

    Thread-safe: SkillStore uses read-only connections for queries.

    Example:
        ```python
        provider = EvolutionMetricsProvider(evolution_store)
        metrics = await provider.get_skill_metrics("pdf-generator")

        if metrics:
            print(f"Total selections: {metrics.total_selections}")
            print(f"Fallback rate: {metrics.fallback_rate:.1%}")
            print(f"Success rate: {metrics.effective_rate:.1%}")
        ```
    """

    def __init__(self, store: "SkillStore"):
        """Initialize provider with evolution store

        Args:
            store: Evolution system's SkillStore instance
        """
        self.store = store

    async def get_skill_metrics(self, skill_id: str) -> "SkillMetrics | None":
        """Get skill funnel metrics from evolution system

        Args:
            skill_id: Skill identifier (must match evolution system's skill_id)

        Returns:
            SkillMetrics with funnel data or None if skill not found

        Notes:
            - Returns None if skill doesn't exist in evolution system
            - Thread-safe: uses read-only connection
            - Performance: < 1ms for local SQLite query
        """
        try:
            # Query evolution store for skill record
            record = self.store.get_skill_by_id(skill_id)

            if record is None:
                logger.debug(f"Skill not found in evolution store: {skill_id}")
                return None

            # Return metrics from record
            logger.debug(
                f"Fetched funnel metrics for {skill_id}: "
                f"selections={record.metrics.total_selections}, "
                f"applied={record.metrics.applied_count}"
            )
            return record.metrics

        except Exception as e:
            # Log warning but don't raise - optimization system should continue
            # even if metrics fetch fails
            logger.warning(f"Failed to fetch metrics for {skill_id}: {e}")
            return None
