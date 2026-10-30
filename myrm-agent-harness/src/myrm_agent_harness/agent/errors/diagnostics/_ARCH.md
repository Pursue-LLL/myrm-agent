# diagnostics/

## Overview
Error diagnostics component. Provides LLM error classification, context extraction, and structured diagnostic results.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Error diagnostics — data types (ErrorContext, DiagnosticResult) and re-exports. | ✅ |
| engine.py | Core | LLMErrorDiagnostic — error classification engine: tries the transport and account families first (connection, tls_certificate, custom_endpoint_unreachable, billing, api_key), then model / custom_model_not_found, rate_limit, response_format_error, context_overflow, timeout, then the provider failures the shared classifier recognizes (overloaded, safety_block, format_error, challenge_blocked), and unknown last. The unknown message carries the provider's own wording (library prefix stripped, truncated). Also the truncation diagnostics (thinking_budget_exhausted, tool_call_truncated, tool_call_retry, text_continuation, text_continuation_exhausted) + provider-stated wait hint (single point in public `diagnose`: seconds/minutes/hours/days, rounded up); the rate-limit diagnosis words the wait once: the generic `rate_limit_wait_step` leads `resolution_steps` only when the provider stated no wait, so the message and the steps never name two different waits + `get_recovery_actions` facade over recovery_actions.py. | ✅ |
| transport_diagnosis.py | Core | `diagnose_transport` — TLS (tls_certificate for rejected or strict-mode certificates, tls_transient for an interrupted handshake) and connection (connection, custom_endpoint_unreachable) families; `infer_service_name` and `extract_port` read the local service and port out of a custom endpoint URL (also used by the model-not-found diagnosis). | ✅ |
| account_diagnosis.py | Core | `diagnose_account` — billing, opencode_training_policy (provider policy rejecting the request) and api_key families. | ✅ |
| catalog_result.py | Core | `build_catalog_result` — the single assembler from an error type to a localized `DiagnosticResult` (message, steps, provider wait appended to the message); transport, account and engine families name the error and leave the wording to the catalogue. | ✅ |
| cooldown_hint.py | Core | `format_cooldown_hint` — renders the provider's wait in the caller's language from the `cooldown_hint_*` locale keys (template + the unit word, singular/plural); seconds stay seconds because the provider reports them that way, and a missing bundle falls back to an English sentence. | ✅ |
| recovery_actions.py | Core | build_recovery_actions — recovery button catalogue: error types with a single-click fix (api_key, billing, model, custom_model_not_found) map to localized {id, label, url} actions; key and model buttons land on `/settings/models`, top-up on `/settings`; other error types have none. | ✅ |
| types.py | Core | ErrorContext and DiagnosticResult (error_type, user_message, resolution_steps, locale) frozen dataclasses for structured LLM error diagnosis. | ✅ |

| Submodule | Description |
|-----------|-------------|
| i18n/ | Framework-level i18n for LLM error diagnostics; bundled `locales/*.json` (en/zh-CN/ja/ko/de), override via `MYRM_LOCALES_DIR` |
