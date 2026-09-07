"""Provider circuit breaker and key pool status telemetry service.

[INPUT]
- myrm_agent_harness.toolkits.llms.fallback.circuit_breaker::get_circuit_breaker_registry
- myrm_agent_harness.toolkits.llms.core.credential_pool::CredentialPool

[OUTPUT]
- ProviderCircuitService: Observability service inspecting and resetting circuit breakers & key pool cooldowns

[POS]
Observability service providing unified introspection of provider/model circuit breaker states,
cooldown timers, and API key pool health metrics.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from myrm_agent_harness.toolkits.llms.fallback.circuit_breaker import (
    get_circuit_breaker_registry,
)

logger = logging.getLogger(__name__)


class ProviderCircuitService:
    """Service for querying and resetting model provider circuit breaker telemetry."""

    def get_all_circuit_statuses(self) -> list[dict[str, Any]]:
        """Get status of all registered circuit breakers with calculated health metrics."""
        registry = get_circuit_breaker_registry()
        raw_stats = registry.get_all_stats()
        now_ts = int(time.time() * 1000)

        results: list[dict[str, Any]] = []
        for name, stat in raw_stats.items():
            state = str(stat.get("state", "closed"))
            failure_count = int(stat.get("failure_count", 0))
            retry_after_ms = int(stat.get("retry_after_ms", 0))
            half_open_calls = int(stat.get("half_open_calls", 0))

            # Determine UX status badge
            if state == "open":
                health = "critical" if retry_after_ms > 10_000 else "warning"
            elif state == "half_open":
                health = "warning"
            else:
                health = "healthy" if failure_count == 0 else "warning"

            results.append(
                {
                    "provider": name,
                    "state": state,
                    "health": health,
                    "failure_count": failure_count,
                    "retry_after_ms": retry_after_ms,
                    "half_open_calls": half_open_calls,
                    "timestamp": now_ts,
                }
            )

        # Sort by status severity: critical -> warning -> healthy, then by provider name
        health_order = {"critical": 0, "warning": 1, "healthy": 2}
        results.sort(key=lambda item: (health_order.get(item["health"], 3), item["provider"]))
        return results

    def reset_circuit(self, provider: str | None = None) -> dict[str, Any]:
        """Reset one or all provider circuit breakers to CLOSED."""
        registry = get_circuit_breaker_registry()
        if provider:
            success = registry.reset_one(provider)
            logger.info("Reset single provider circuit breaker '%s': %s", provider, success)
            return {
                "success": success,
                "reset_count": 1 if success else 0,
                "provider": provider,
            }

        reset_count = registry.reset_all()
        logger.info("Reset all provider circuit breakers, count: %d", reset_count)
        return {
            "success": True,
            "reset_count": reset_count,
            "provider": None,
        }


provider_circuit_service = ProviderCircuitService()
