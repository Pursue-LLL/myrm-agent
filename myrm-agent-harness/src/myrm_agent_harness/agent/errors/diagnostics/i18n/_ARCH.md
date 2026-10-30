# i18n/

## Overview
Framework-level i18n for LLM error diagnostics. Bundled JSON locales (en/zh-CN/ja/ko/de); override via `MYRM_LOCALES_DIR`. Business layers may extend via `register_translations()`. A text is read along `LocaleManager.locale_chain()`: the requested locale, Simplified Chinese for any Chinese locale (no Traditional Chinese bundle ships), then English.

## File & Submodule Index

| File / Dir | Role | Description | I/O/P |
|------------|------|-------------|-------|
| __init__.py | Package | Re-exports LocaleManager and get_locale_manager singleton | ✅ |
| constants.py | Config | REQUIRED_ERROR_TYPES for completeness validation | ✅ |
| manager.py | Core | LocaleManager — detection, bundled JSON load, formatting. Flat keys `<error_type>_user_message` / `_resolution_steps` / `_wait_step` and `cooldown_hint_*` are unflattened per error type; `translate_optional` returns None for a text a custom bundle does not carry, so a caller can leave the text out instead of showing a missing-translation marker. `locale_chain()` is the one place the language fallback is defined, shared with `cooldown_hint.py`. A template `str.format` rejects (`{}`, `{model`, `{x[a]}`) counts as absent for its language: `translate` and `translate_optional` go on to the next language of the chain and log a warning with the traceback, a step list with one such step is set aside whole, and a text no language of the chain renders takes the missing-translation path | ✅ |
| locales/ | Data | Bundled flat JSON locale files shipped with the wheel | — |
| locales/en.json | Data | English diagnostic strings | — |
| locales/zh-CN.json | Data | Simplified Chinese diagnostic strings | — |
| locales/ja.json | Data | Japanese diagnostic strings | — |
| locales/ko.json | Data | Korean diagnostic strings | — |
| locales/de.json | Data | German diagnostic strings | — |

## Module Dependencies

- No dependency on `myrm-agent-server`; locales are self-contained in `locales/`
