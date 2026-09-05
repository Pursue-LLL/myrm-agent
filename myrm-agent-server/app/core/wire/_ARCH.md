# wire/

## Overview
Business-layer model → wire protocol routing and defaults.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| registry.py | Core | OpenCode-scoped routing (`WireEndpointContext`: `provider_id==opencode_go` OR `base_url` gate + model patterns) | ✅ |
| defaults.py | Core | Wire-aware model_kwargs defaults (min output, reasoning effort, reasoning.encrypted_content include; Vercel AI Gateway attribution headers & custom_llm_provider normalization) | ✅ |
| enrich.py | Core | Apply routing + defaults to `ModelConfig` at resolve time (accepts resolve-time `provider_id`) | ✅ |

## POS
Injected from `model_resolver` and `_resolve_model_config`. Routing is scoped to OpenCode via `WireEndpointContext`; harness owns HTTP transport.
