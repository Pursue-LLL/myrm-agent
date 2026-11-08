# fallback/

## Overview
Enhanced model fallback management. Supports cooldown periods and candidate pools.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Enhanced model fallback management. Supports cooldown periods and candidate pools | ✅ |
| config.py | Config | Configurable probe and cooldown policies for model fallback management. | ✅ |
| context.py | Core | Async-context-bound emitter binding via ContextVar. Lets business surfaces (SSE, telemetry) subscribe to failover/recovery events without coupling the manager to any transport. | ✅ |
| events.py | Core | Defines failover and recovery events that are emitted during model lifecycle. | ✅ |
| health_check.py | Core | `lightweight_health_check` (model typed by the `ProbeTarget` protocol): one trivial request cancelled at a hard `asyncio.wait_for` deadline (default 5 s), used to probe cooled-down failover candidates and by the server's reachability check. The model's own request timeout (minutes) never applies, and no output-token cap is forced (reasoning models reject one), so the deadline bounds the probe's cost. `probe_llm_health` returns the same probe as a `HealthProbeResult` that classifies the failure (`timeout` vs `provider_error`) and keeps the upstream reason, so a caller can explain *why* a provider is unreachable instead of reporting "no response". | ✅ |
| managed_llm.py | Core | LLM wrapper that transparently integrates ModelFallbackManager into LangChain's | ✅ |
| manager.py | Core | Model fallback manager. Maintains candidate pool, cooldown state, and selects the next available mod | ✅ |
| probe_throttle.py | Core | Global probe throttle. Prevents concurrent requests from redundantly probing the same model. | ✅ |
| recommendations.py | Core | Provides intelligent fallback model recommendations based on model capabilities, | ✅ |
| scenario.py | Core | Scenario-aware model selection. Optimizes model choice based on scenario (realtime/batch/balanced). | ✅ |

## Key Dependencies

- `infra`
