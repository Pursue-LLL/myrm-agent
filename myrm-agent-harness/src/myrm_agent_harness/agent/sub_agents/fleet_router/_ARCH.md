# fleet_router/

## Overview

Fleet-wide profile rail and multi-gateway router. Spreads subagent work across several
gateway endpoints, keeps one reusable connection pool, and relays artifacts between
gateways so a task that starts on one endpoint can finish on another.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the router, pool, relay and context injector. | — |
| connection_pool.py | Core | `MultiGatewayConnectionPool` — per-gateway connection reuse with health tracking. | — |
| context_injector.py | Core | Injects the gateway-scoped context each routed subagent needs. | — |
| artifact_relay.py | Core | `CrossGatewayArtifactRelayService` — content-addressed artifact hand-off between gateways. | — |
| types.py | Core | `GatewayStatus`, pool/relay request and result models. | — |

## Key Dependencies

- `pydantic` (models)
- `sub_agents.types` (subagent configuration used when routing)

## Key Design Decisions

- **Gateway status is explicit**: `GatewayStatus` carries the lifecycle so callers can skip a
  degraded endpoint instead of failing the whole fleet.
- **Artifacts are content-addressed**: the relay hashes payloads, so the same artifact relayed
  twice is stored once.
- **Pool owns reuse only**: the pool never decides routing; routing policy stays in the caller.
