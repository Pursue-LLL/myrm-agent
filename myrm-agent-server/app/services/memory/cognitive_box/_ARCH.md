# Server Cognitive Box Service Architecture

## Role
Provides the single-instance backend lifecycle for the four-layer cognitive context memory box.

## Boundaries
- Belongs to `myrm-agent-server` service tier.
- Integrates `CognitiveMemoryBoxService` from harness memory toolkit via top-level imports.
- Exposes singletons through FastAPI `Depends` for cognitive box endpoints.
