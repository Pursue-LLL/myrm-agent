# infra/

## Overview
Infrastructure layer.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Infrastructure layer. | — |
| atomic_write.py | Core | Atomic file write with crash-consistency guarantee. | ✅ |
| data_dir.py | Core | `resolve_data_dir()`: the single resolver of the Myrm state root (`$MYRM_DATA_DIR`, default `~/.myrm`). Every Myrm-owned persistent path derives from it so an isolated process never touches another process's data; enforced by `tests/architecture/test_state_paths_follow_data_dir.py`. | ✅ |
| sqlite_backup.py | Core | SQLite hot-backup manager with integrity verification, SHA-256 checksum, quarantine, and manifest tracking; `hot_copy_database` is the standalone online page-wise copy it shares with `state_archive/`. | ✅ |
| sqlite_backup_models.py | Core | Data models and low-level SQLite PRAGMA utilities for sqlite_backup snapshots, verification, and restore results; also the temporary-image lifecycle: an interrupted or failed backup removes its `.tmp-` image and SQLite sidecars, and each backup first sweeps images idle for more than 5 minutes (left by a killed process). | ✅ |
| sqlite_salvage.py | Core | SQLite non-destructive B-Tree page-skipping rowid salvage engine with binary search bad page isolation, orphan session stub healing, native FTS rebuild, and deferred secondary index/view replay. | ✅ |
| tls_compat.py | Core | Enterprise network compatibility (`MYRM_TLS_STRICT=0`) for Python 3.13+/OpenSSL 3.x behind corporate TLS-inspection proxies. `apply_global_tls_relaxation()` wraps `ssl.create_default_context` once and points `ssl._create_default_https_context` at the wrapper, so every library that builds its context there (httpx, litellm's aiohttp transport, `urllib.request`, `http.client`) is covered: client-purpose contexts then trust the operating-system store (`truststore`) plus any CA bundle named by `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` / `NODE_EXTRA_CA_CERTS`, with only `VERIFY_X509_STRICT` cleared (chain, hostname and expiry checks stay on); callers that pass an explicit CA file, directory or data keep exactly that trust, except that the file `SSL_CERT_FILE` names is the environment's bundle wherever it is passed from (httpx, httpx2 and litellm read it themselves and hand it over as a CA file) and is added like the others. Libraries that built their own context are brought under the same policy: aiohttp's import-time default context is rebuilt through the wrapper, litellm's already-cached contexts are discarded, and urllib3 (`requests`, for example the Feishu SDK) gets the same trust, the class its builder instantiates becoming a factory and every urllib3 module holding the builder being rebound to a version that adds the environment's CA bundles and clears the strict flag (a CA file a caller loads on top, such as `verify=path`, is added to that trust, not exclusive). The setting is read when a context is created and installed at host startup, so clients already built keep their context and a change needs a restart. A client that constructs `ssl.SSLContext` itself is outside the policy. The MCP SDK's own transport (httpx2) builds its context with `truststore` and reaches the wrapper only when `SSL_CERT_FILE` is set, so `REQUESTS_CA_BUNDLE` / `NODE_EXTRA_CA_CERTS` reach it only beside `SSL_CERT_FILE`. A CA directory named by `SSL_CERT_DIR` is an explicit CA directory and keeps replacing the trust. A child process inherits none of this, so `with_node_system_ca()` adds `NODE_USE_SYSTEM_CA=1` to the environment of a child that may run Node (Node 22.19+ and 24.6+ read it; an older Node ignores it) while the setting is on, and a value the caller sets wins (case-insensitively on Windows); it is called by `toolkits/mcp/placeholders.py` (stdio servers), `toolkits/acp/runtime/_base.py` (`build_safe_env`, the environment of delegated CLI agents) and `toolkits/acp/toolchains/manager.py` (the npm install child). `create_httpx_client()` is a thin `httpx.AsyncClient` factory; a client constructed directly is covered by the policy just the same. | ✅ |
| tls_error_signals.py | Core | The single list of certificate-rejection and interrupted-handshake wordings: `is_tls_hard_error()` (a rejected chain, permanent and never retried) and `is_tls_transient_error()` (a handshake interrupted before any certificate verdict; a hard signal always wins), read by the LLM failure classifier (`toolkits/llms/errors/tls_rejection.py`) and the error diagnostics (`agent/errors/diagnostics/transport_diagnosis.py`). | ✅ |
| cooperative_signals.py | Core | Cooperative pause probe token (`CooperativePauseSignal`) for background maintenance yield. Imported by `toolkits/memory/` and `runtime/cognitive_clock/`. | ✅ |

| Submodule | Description |
|-----------|-------------|
| delivery/ | Durable delivery persistence and dead-letter retry; the delivery queue is owned by the host. |
| git/ | Pure-Python zero-subprocess Git metadata resolver (branch, commit, worktrees, detached HEAD) with mtime debounce. |
| incremental/ | Incremental state tracking for monitoring data changes. |
| health/ | Health checking infrastructure. Abstract interfaces for resource health checks and automatic recovery. |
| pubsub/ | Generic in-process pub-sub (`PubSubBus`); Server SSE / pairing / btw. Distinct from `runtime/events/` and `agent/streaming/broadcast/`. |
| state_archive/ | Consistent SQLite snapshots, verified zip archive (manifest + payload) and journaled, crash-recoverable promotion of a staged tree into a live root. Generic mechanism only; callers own path classification. |
| tracing/ | OpenTelemetry distributed tracing. Distinct from `observability/tracing/` (stdlib log trace_id). |

## Key Dependencies

- `utils` (logger, files)
