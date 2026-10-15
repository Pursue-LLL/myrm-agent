/**
 * [INPUT]
 * - (none; imported by next.config.ts, so it must stay free of `@/` aliases and runtime dependencies)
 *
 * [OUTPUT]
 * - LONG_RUNNING_REQUEST_TIMEOUT_MS: client and rewrite-proxy ceiling for synchronous calls that run LLM work per item.
 *
 * [POS]
 * Single source of the long-request ceiling shared by the API client (per-call `timeout`) and the Next rewrite proxy
 * (`experimental.proxyTimeout`). Both default to 30s and either one alone cuts the call while the backend keeps running.
 */

/** Wiki full maintenance runs up to 20 sequential LLM calls (about 60s each on slow reasoning models); 30 minutes bounds it with margin. */
export const LONG_RUNNING_REQUEST_TIMEOUT_MS = 30 * 60 * 1000;
