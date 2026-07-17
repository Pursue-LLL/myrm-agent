# Dev Gate API Module

## Purpose

Localhost-only diagnostic endpoints for development tooling (e.g. Chrome MCP E2E tests, `./myrm ready` health checks). These endpoints aggregate readiness probes and are **never exposed to production traffic**.

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/api/v1/dev-gate/readiness` | GET | Aggregate readiness check (provider, edge-tts, config) |

## Security

All endpoints enforce `is_loopback_client()` — requests from non-loopback IPs receive **403 Forbidden**.

## Dependencies

- `app.api.config.router.get_config_readiness` — provider & config status
- `app.api.health.router.system_info` — deploy mode & system health
- `app.api.health.router._check_edge_tts_installed` — TTS availability
