# core/security/guards/

## Overview
Session-level security guards — privacy tracking, SSRF prevention, and skill DLP domain allowlist.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Module exports for core security guards: privacy ladder, privacy tracker, ssrf, and url allowlist. | ✅ |
| privacy_ladder.py | Core | Privacy fail-closed ladder — 3-level hierarchy (Workspace -> Session -> File) for sandboxed persistence and mutations. `PrivacyScope.restricted_patterns` defaults to `core.security.path::SENSITIVE_FILE_PATTERNS`, so the persistence gate and the shell, file-tool and snapshot channels judge credentials by one rule list. | ✅ |
| privacy_tracker.py | Core | Privacy tracker — per-turn PII sensitivity tracking (`record` notes every detection; `escalate` notes one only when it lifts the turn level, for content rescanned on every model call), ContextVar-based privacy policy access (set/get_privacy_policy). | ✅ |
| ssrf.py | Core | Unified outbound URL SSRF validation — sync/async validate, RFC 3986 compliant IPv6 DNS-pinned URLs, SSRF_BLOCKED audit on block. `async_vetted_addresses` returns the public addresses a host resolves to for a client that keeps the host name in the URL and connects only to them (web_fetch's HTTP tier); `async_pin_url` shares the check and rewrites the URL to the first address for clients that cannot. HTTP fetch: `core/security/http/secure_fetch.py`. | ✅ |
| url_allowlist.py | Core | ContextVar-based skill `allowed-domains` DLP guard for outbound HTTP — supports a leading-dot wildcard; the host and every allowed domain are compared in canonical spelling (`domain_match.canonical_name`), so a Unicode entry and the Punycode host a client dials are one domain. | ✅ |

## Key Dependencies

- `utils/url_utils/` — `is_blocked_ip`, `validate_scheme_and_hostname` (primitives only); `utils/url_syntax.py` — `parse_outbound_hostname`, `canonical_hostname` (canonical spelling and syntax check shared with policies that have no hostname blocklist)
- `core/security/domain_match.py` — `canonical_name`, the spelling of a host and of an allowed domain, the one the domain lists use
- `core/security/audit.py` — `record_decision` for SSRF_BLOCKED entries
- No `agent/` imports (toolkits gate)
