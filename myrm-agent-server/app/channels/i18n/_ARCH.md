# i18n/

## Overview
Internationalization for channel static messages and shared JSON/Fluent catalogs. Supports BCP 47 locale fallback, recursive JSON flattening (for nested next-intl-style keys), and safe template formatting when kwargs are missing. A requested locale is served from the first fallback that has a catalog, so a regional variant shares the catalog (and the cached `FluentLocalization`) of its language and a string that names no catalog never becomes a file path or a cache key.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Exports `channel_t`/`add_locale_root`; defines `get_text`/`resolve_message_locale`/`get_locale_from_metadata` and the shared `_locale_from_meta` resolution helper. | — |
| engine.py | Core | Fluent + JSON dual engine: `SafeDict` formatting, deep flatten, locale roots, and `_resolve_locale` (requested locale → the language whose catalog serves it). | ✅ |
| locales/ | Data | Channel static catalogs: `.ftl` (slash commands, search gates, `daily_budget_blocked`, `channel_budget_blocked`, `approval_reason_<code>` (one sentence per harness approval reason code, in en/ja/zh-CN/zh-TW)…) and `.json` (server channel-only keys: `stuck_task_timeout_user_message`, `risk_outbound_blocked`, `risk_inbound_blocked`). LLM error diagnostics belong to the harness catalog (`myrm_agent_harness.agent.errors.diagnostics.i18n`), NOT duplicated here. | — |

## Locale Roots (priority: first registered wins)

1. `locales/` (this package) — server channel messages (slash commands, risk gates, task timeout).
2. Optional `add_locale_root()` — host app may register extra catalogs (e.g. channel-specific server messages only when no GUI).

Catalog names are the `.json` / `.ftl` file stems across the roots. They are read on first use and again after each `add_locale_root()`; a catalog file added to an already registered root is recognised after the next `add_locale_root()` or restart.

## Key Dependencies

- `fluent.runtime` (FluentLocalization)
- Host apps with channel-only strings: call `add_locale_root()` at startup (Web UI strings belong in frontend `locales/`, not shared with server)
