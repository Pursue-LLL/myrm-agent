# redact/

## Overview

Secret redaction domain — masks API keys, tokens and credentials before they reach the LLM context or log files (Layer 2 output redaction).
`masking.py` holds the value masking (a password or passphrase is hidden completely, a token keeps its head and tail), `patterns.py` the compiled regexes and shared replacers, `structured_fields.py` masks credential-named fields in JSON, JSON nested in a JSON string and Python repr diagnostics under one key policy, `engine.py` owns the bounded-replace pipeline and public APIs.
`__init__.py` is the aggregation facade exposing the public `core.security.redact` import surface.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Aggregation facade — re-exports engine + shared helpers (`_mask_token`). | ✅ |
| masking.py | Core | Leaf value masking — `_mask_token` hides a value under 18 characters completely and keeps the head 6 and tail 4 of a longer one (the head of a machine-issued token names its issuer, the rest is random); `_mask_secret(name, value)` hides the value of a password or passphrase (a name containing `pass` or `pw`) completely whatever its length, since the head and tail of a phrase a person chose disclose most of it. Every value replacer asks it by credential name; a name that merely contains `pass` (`bypass_token`) is hidden completely too, which errs on the side of showing less. | ✅ |
| patterns.py | Core | Compiled detection regexes (token prefixes, ENV/Auth/header/URL userinfo/query/bare-token/JWT, YAML/colon + form-urlencoded configs, CLI `=` flags, control chars), word-boundary key validation, form-body / ENV/YAML/CLI replacers. An unquoted value runs to whitespace or a quote, and a `&` ends it only before a `key=` pair or `amp;` (the shared `_UNQUOTED_VALUE`), so `PASSWORD=ab&cd` is masked whole while `token=abc&page=1` keeps `page=1`; a value cannot start with `&`, which keeps the YAML anchor in `password: &anchor`. The credential-name lists (ENV, YAML, keyword guard, CLI flags; the JSON list lives in `structured_fields.py`) each carry `passphrase`, and the lower-case `name_key=` detector bounds the name on both sides so a long underscore-and-keyword run costs time proportional to its length. A value that is entirely a variable reference (`$DB_PASS`, `${db_pass}`, `${X:?msg}`, `${X:-}`; a bare `$NAME` must be upper case, a non-empty `:-default` is a literal, and a literal after the closing `}` keeps the value masked) is kept by `_is_env_reference`, so compose/script variable names stay readable while `$Secret123` is still masked; the one known gap is a real password written as an upper-case `$WORD`. | ✅ |
| structured_fields.py | Core | Credential-named field masking — plain JSON member (`_JSON_FIELD_RE`, shared with the skill content sanitizer), JSON member inside a JSON-encoded string (any escape depth), Python `repr` entries on pytest/exception diagnostic lines only. One key policy (`_is_secret_field_name`): bare credential words or an unambiguous credential noun suffix in snake/kebab/dotted/camel/Pascal spelling; bare `token`/`secret` are never suffix-matched, so `nextPageToken` / `token_count` stay readable. The noun list covers cloud-CLI credentials such as AWS `SecretAccessKey`, the backup and key-tool noun `passphrase`, and the channel credential nouns `app secret`, `signing secret`, `bot token`, `verification token` (vendor-neutral). Locale files key their form labels by those names (`"feishuAppSecret": "App Secret"`), so under a channel noun a value that is a plain label (`_PLAIN_LABEL_RE`: letters of any script joined by spaces, `-` or `_`, no digits, a lone word under 20 characters) is kept; every other name masks a label-shaped value like any other, and a passphrase made of words, a short letters-only value, or a random URL-safe base64 value without a digit under a channel noun is the known gap. A value that is a variable reference (`${API_KEY}`) is kept. An empty or blank plain-JSON value is left as written ("not set" is no secret and a reader needs it). | ✅ |
| engine.py | Core | Redaction engine — bounded replace (ReDoS guard), control-split token guard, `redact_sensitive_text`, `RedactingFormatter`, `escape_invisible_unicode`, `redact_for_llm`, `redact_for_display`. | ✅ |

## Key Dependencies

- None within `core.security` (foundation layer); the privacy tier's vendor-prefix table in `detection/leak_detector.py` is separate and maintained on its own
- Inside the package: `__init__.py` imports `engine.py` and `masking.py`; `engine.py` imports `masking.py`, `patterns.py` and `structured_fields.py`; `structured_fields.py` imports `masking.py` and `patterns.py`; `patterns.py` imports `masking.py` and `re`; `masking.py` imports only `re`

## Consumers

- `agent/security/redact.py` — thin facade re-exporting public + internal symbols
- `agent/skills/security/content_sanitizer.py` — imports `patterns.py` regexes, the `_redact_value` key guard and `structured_fields._JSON_FIELD_RE` for structured content masking; its rule table names the capture group of each regex, so a change to a regex's group layout must be mirrored there (`tests/agent/skills/test_content_sanitizer.py` fails when a secret survives); it inherits the channel nouns of `_JSON_FIELD_RE` without the label exemption, which only shows a placeholder such as `"bot_token": "your-bot-token"` as a reviewable finding in the export preview
- `utils/errors.py`, `toolkits/browser/exceptions.py` — `redact_for_llm`
- `agent/middlewares/approval/_interrupt_payload.py` — `redact_for_display`
- toolkits across browser / web_fetch / mcp / code_execution / memory — `redact_sensitive_text`
