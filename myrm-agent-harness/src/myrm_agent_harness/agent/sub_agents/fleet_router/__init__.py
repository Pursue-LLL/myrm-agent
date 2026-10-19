"""Fleet-wide profile rail and multi-gateway router package.

[INPUT]
- (none: package re-exports only)

[OUTPUT]
- MultiGatewayConnectionPool, HostGatewayContextInjector, CrossGatewayArtifactRelayService
- Gateway and artifact models from `.types`

[POS]
Public surface of the fleet router. Keeps the pool, injector and relay importable from one
package name so callers do not reach into the modules directly.
"""

from myrm_agent_harness.agent.sub_agents.fleet_router.artifact_relay import (
    CrossGatewayArtifactRelayService,
)
from myrm_agent_harness.agent.sub_agents.fleet_router.connection_pool import (
    DuplicateGatewayError,
    FleetRouterError,
    GatewayNotFoundError,
    GatewayOfflineError,
    MultiGatewayConnectionPool,
)
from myrm_agent_harness.agent.sub_agents.fleet_router.context_injector import (
    HostGatewayContextInjector,
)
from myrm_agent_harness.agent.sub_agents.fleet_router.types import (
    CrossGatewayArtifactEnvelope,
    FleetProfile,
    FleetTopologySnapshot,
    GatewayNode,
    GatewayPlatform,
    GatewayStatus,
    GatewayTelemetry,
    OfflineBufferedCommand,
)

__all__ = [
    "GatewayStatus",
    "GatewayPlatform",
    "GatewayTelemetry",
    "GatewayNode",
    "FleetProfile",
    "OfflineBufferedCommand",
    "CrossGatewayArtifactEnvelope",
    "FleetTopologySnapshot",
    "FleetRouterError",
    "GatewayNotFoundError",
    "GatewayOfflineError",
    "DuplicateGatewayError",
    "MultiGatewayConnectionPool",
    "HostGatewayContextInjector",
    "CrossGatewayArtifactRelayService",
]
