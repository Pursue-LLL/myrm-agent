# redact/

## Overview

Secret redaction domain — masks API keys, tokens, and credentials before they
reach the LLM context or log files (Layer 2 output redaction). Four files by
concern: `patterns.py` holds the compiled regexes (also consumed by
`agent/skills/security/content_sanitizer.py`; the privacy tier's vendor-prefix
table in `detection/leak_detector.py` is separate); `structured_fields.py`
masks credential-named fields in JSON, JSON nested in a JSON string and Python
repr diagnostics under one key policy; `engine.py` owns the bounded-replace
pipeline and public APIs; `__init__.py` is the aggregation facade exposing the
public `core.security.redact` import surface.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Aggregation facade — re-exports engine + shared helpers (`_mask_token`). | ✅ |
| patterns.py | Core | Compiled detection regexes (token prefixes, ENV/Auth/header/URL userinfo/query/bare-token/JWT, YAML/colon + form-urlencoded configs, CLI `=` flags, control chars), word-boundary key validation, `_mask_token` / form-body / ENV/YAML/CLI replacers. | ✅ |
| structured_fields.py | Core | Credential-named field masking — plain JSON member (`_JSON_FIELD_RE`, shared with the skill content sanitizer), JSON member inside a JSON-encoded string (any escape depth), Python `repr` entries on pytest/exception diagnostic lines only. One key policy (`_is_secret_field_name`): bare credential words or an unambiguous credential noun suffix in snake/kebab/dotted/camel/Pascal spelling; bare `token`/`secret` are never suffix-matched, so `nextPageToken` / `token_count` stay readable. An empty or blank plain-JSON value is left as written ("not set" is no secret and a reader needs it). | ✅ |
| engine.py | Core | Redaction engine — bounded replace (ReDoS guard), control-split token guard, `redact_sensitive_text`, `RedactingFormatter`, `escape_invisible_unicode`, `redact_for_llm`, `redact_for_display`. | ✅ |

## Key Dependencies

- None within `core.security` (foundation layer)

## Consumers

- `agent/security/redact.py` — thin facade re-exporting public + internal symbols
- `agent/skills/security/content_sanitizer.py` — imports `patterns.py` regexes, the `_redact_value` key guard and `structured_fields._JSON_FIELD_RE` for structured content masking; its rule table names the capture group of each regex, so a change to a regex's group layout must be mirrored there (`tests/agent/skills/test_content_sanitizer.py` fails when a secret survives)
- `utils/errors.py`, `toolkits/browser/exceptions.py` — `redact_for_llm`
- `agent/middlewares/approval/_interrupt_payload.py` — `redact_for_display`
- toolkits across browser / web_fetch / mcp / code_execution / memory — `redact_sensitive_text`
