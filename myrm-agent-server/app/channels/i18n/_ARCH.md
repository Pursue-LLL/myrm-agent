# i18n/

## Overview
Internationalization for channel static messages and shared JSON/Fluent catalogs. Supports BCP 47 locale fallback, recursive JSON flattening (for nested next-intl-style keys), and safe template formatting when kwargs are missing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports `channel_t`, `add_locale_root`, locale resolution helpers. | — |
| engine.py | Core | Fluent + JSON dual engine: `SafeDict` formatting, deep flatten, locale roots. | ✅ |
| locales/ | Data | Harness default `.ftl` and LLM error diagnostic `.json` catalogs. Channel static keys include slash commands, search gate messages, and `daily_budget_blocked` (en/zh-CN `.ftl`; other locales fall back to en). | — |

## Locale Roots (priority: first registered wins)

1. `locales/` (this package) — harness defaults (slash commands, error diagnostics).
2. Optional `add_locale_root()` — host app may register extra catalogs (e.g. channel-specific server messages only when no GUI).

## Key Dependencies

- `fluent.runtime` (FluentLocalization)
- Host apps with channel-only strings: call `add_locale_root()` at startup (Web UI strings belong in frontend `locales/`, not shared with server)
