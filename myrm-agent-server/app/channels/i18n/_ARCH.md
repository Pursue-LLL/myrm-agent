# i18n/

## Overview
Internationalization for channel static messages and shared JSON/Fluent catalogs. Supports BCP 47 locale fallback, recursive JSON flattening (for nested next-intl-style keys), and safe template formatting when kwargs are missing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports `channel_t`/`add_locale_root`; defines `get_text`/`resolve_message_locale`/`get_locale_from_metadata` and the shared `_locale_from_meta` resolution helper. | — |
| engine.py | Core | Fluent + JSON dual engine: `SafeDict` formatting, deep flatten, locale roots. | ✅ |
| locales/ | Data | Channel static catalogs: `.ftl` (slash commands, search gates, `daily_budget_blocked`, `channel_budget_blocked`…) and `.json` (server channel-only keys: `stuck_task_timeout_user_message`, `risk_outbound_blocked`, `risk_inbound_blocked`). LLM error diagnostics belong to the harness catalog (`myrm_agent_harness.agent.errors.diagnostics.i18n`), NOT duplicated here. | — |

## Locale Roots (priority: first registered wins)

1. `locales/` (this package) — server channel messages (slash commands, risk gates, task timeout).
2. Optional `add_locale_root()` — host app may register extra catalogs (e.g. channel-specific server messages only when no GUI).

## Key Dependencies

- `fluent.runtime` (FluentLocalization)
- Host apps with channel-only strings: call `add_locale_root()` at startup (Web UI strings belong in frontend `locales/`, not shared with server)
