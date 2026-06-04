# matrix/

## Overview
Matrix channel provider with optional End-to-End Encryption (E2EE).
Uses the mautrix Python SDK for Client-Server API, /sync event loop,
and OlmMachine-based Olm/Megolm cryptography.

Supports: token-based and password-based authentication, DM identification
via m.direct account data (with runtime refresh on auto-join), encrypted
attachment upload/download, proxy configuration (HTTP/HTTPS/SOCKS5),
cross-signing bootstrap, and room-members cache with TTL.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports MatrixChannel. | — |
| channel.py | Core | MatrixChannel class. Lifecycle, credential_spec, outbound text send/edit/delete/react, typing, health_check, collect_issues. | ✅ |
| auth.py | Core | Authentication and initialization. aiohttp session creation (with proxy), token/password login, initial /sync, DM cache (in-place mutation with runtime refresh). | ✅ |
| handlers.py | Core | Inbound event handling. m.room.message processing, invite auto-join, background /sync loop. | ✅ |
| crypto.py | Core | E2EE initialization. OlmMachine setup with SQLite CryptoStore, device key verification, cross-signing bootstrap, recovery key import, cleanup. | ✅ |
| media.py | Core | Media upload and send. File upload, mxc:// pass-through, E2EE attachment encryption. | ✅ |
| html.py | Helper | Markdown → Matrix HTML conversion (org.matrix.custom.html). Code blocks, inline formatting, mentions, blockquotes, lists. Zero external deps. | ✅ |

## Dependencies

- **Install**: `uv sync --extra matrix` (mautrix + aiohttp-socks); E2EE add `--extra matrix-e2ee`
- **Required**: `mautrix>=0.21.0` (Matrix Client-Server API SDK)
- **E2EE**: `mautrix[encryption]>=0.21.0` (adds `python-olm`, requires `libolm` C library)
- **SOCKS proxy**: `aiohttp-socks` (declared in `[project.optional-dependencies] matrix`)

## Architecture

```
credential_spec → from_credentials() → MatrixChannel.__init__()
                                              │
              ┌───────────────────────────────┤
              ▼                               ▼
       authenticate()              setup_e2ee() [crypto.py]
       [auth.py]                   (OlmMachine + CryptoStore)
       (token or password)                    │
              │                               │
              └───────────┬───────────────────┘
                          ▼
                  initial_sync() [auth.py]
                  (populate rooms, DM cache)
                          │
                          ▼
                  run_sync_loop() [handlers.py]
                  (mautrix Client.sync())
                          │
                  ┌───────┴────────┐
                  ▼                ▼
    handle_room_message()    handle_invite()
    [handlers.py]            [handlers.py]
    (→ _emit_inbound)        (→ auto_join)
```

## E2EE Graceful Degradation

Two levels (no httpx fallback — clean architecture):
1. **mautrix without E2EE**: `encryption=false` or `mautrix[encryption]` not installed.
   Works in plaintext rooms only. Encrypted messages are silently ignored.
2. **mautrix with E2EE**: `encryption=true` and `mautrix[encryption]` installed.
   Full E2EE support: Olm/Megolm sessions, encrypted attachments, cross-signing.
