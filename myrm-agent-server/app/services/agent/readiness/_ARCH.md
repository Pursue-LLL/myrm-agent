# readiness/

## Overview
Per-agent configuration readiness resolver — proactive dry-run before Agent execution.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Re-exports ReadinessLevel, AgentReadinessItem, AgentReadinessReport, resolve_agent_readiness, get_readiness_resolver | — |
| `resolver.py` | Core | 6-dimension readiness checker (model/mcp/skills/tools/search/deployment) + MCP scoped-secret preflight; static config checks; TTL-cached singleton | ✅ |

## Architecture

- **No harness dependency**: All checks are business-layer logic (profile_resolver, config_readiness, MCP service)
- **Reuses existing checkers**: ProviderConfigChecker for model dimension
- **Three-tier levels**: ready / warning / blocked
- **MCP check**: Static config match — compares agent's mcp_ids against configured MCP servers; the configured set covers both the user's own config (`mcpServers`) and org-managed servers pushed by the Control Plane (`orgMcpServers`), matching the runtime merge via `config_parsers.merge_org_mcp_configs` (shared by every execution entry point). Bound servers that declare `requiredSecrets` or `{{secret:KEY}}` header references are cross-checked against the agent vault (via `DatabaseSecretBackend.list_secret_keys`, key names only — no decryption), and missing keys surface as a WARNING with a deep-link to the agent Secrets tab (`/settings/agents?agentId={id}#secrets`)
- **Deep-links**: Agent-dimension items deep-link to `/settings/agents?agentId={id}#loadout` (capabilities tab) or `#secrets` (secrets tab) via `_agent_settings_path`, matching the frontend `agentSettingsHref` canonical route; global-dimension items deep-link to their settings tab (e.g. `/settings/mcp`, `/settings/models`, `/settings/search`)
- **Cache**: 5min TTL, invalidated on Settings save via frontend
- **API**: `GET /api/user-agents/{agent_id}/readiness` — consumed by Composer Badge + Settings Agent page

## Key Dependencies

- `app.services.agent.profile.profile_resolver` (ResolvedAgentProfile SSOT)
- `app.core.channel_bridge.config_readiness` (ProviderConfigChecker)
- `app.core.channel_bridge.config_loader` (load_user_configs)
- `app.core.channel_bridge.config_parsers` (extract_mcp_configs / merge_org_mcp_configs)
- `app.services.agent.backends.secret_backend` (DatabaseSecretBackend / `list_secret_keys`)
- `app.services.skills.evolution_review.disk` (get_skill_store)
