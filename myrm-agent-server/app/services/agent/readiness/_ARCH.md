# readiness/

## Overview
Per-agent configuration readiness resolver — proactive dry-run before Agent execution.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Re-exports ReadinessLevel, AgentReadinessItem, AgentReadinessReport, resolve_agent_readiness, get_readiness_resolver | — |
| `resolver.py` | Core | 6-dimension readiness checker (model/mcp/skills/tools/search/deployment); static config checks; TTL-cached singleton | ✅ |

## Architecture

- **No harness dependency**: All checks are business-layer logic (profile_resolver, config_readiness, MCP service)
- **Reuses existing checkers**: ProviderConfigChecker for model dimension
- **Three-tier levels**: ready / warning / blocked
- **MCP check**: Static config match — compares agent's mcp_ids against user's configured MCP servers
- **Cache**: 5min TTL, invalidated on Settings save via frontend
- **API**: `GET /api/user-agents/{agent_id}/readiness` — consumed by Composer Badge + Settings Agent page

## Key Dependencies

- `app.services.agent.profile_resolver` (ResolvedAgentProfile SSOT)
- `app.core.channel_bridge.config_readiness` (ProviderConfigChecker)
- `app.core.channel_bridge.config_loader` (load_user_configs)
- `app.services.mcp.mcp_service` (MCP config lookup)
- `app.services.skills.skill_service` (Skill existence check)
