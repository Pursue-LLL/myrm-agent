# fetchers/

## Overview
Toolkits Web_Fetch Fetchers module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| browser_fetcher.py | Core | Provides BrowserFetcher. A navigation the SSRF policy blocks raises `SSRFSecurityError` (never degrades to another tier); each fetch gets its own explicit-origin grants because pooled CRAWL contexts outlive it. | ✅ |
| http_fetcher.py | Core | L1 HTTP fetcher (Scrapling curl_cffi). HTTP/2 default; HTTP/3 retry on 403/antibot/empty only; skipped with proxy pool. SSRF defense through `FetchTargetGuard` on every hop (the requested URL and each redirect `Location`): a hop is judged and requested in its canonical spelling (`canonical_url`), so libcurl connects to the host the policy classified. Under the cloud policy the request is pinned to the resolved address, and when it fails (an HTTPS certificate names the host, not the address) it is retried by the canonical name, which resolves again; a rejected hop raises `SSRFSecurityError` instead of returning None, so the engine does not retry the same URL on a browser tier. Only text bodies are truncated (`MAX_TEXT_BODY_BYTES`) to bound the HTML pipeline; non-text bodies stay whole as `raw_body` because a truncated PDF or Office file cannot be parsed, and the binary router enforces their size limit. | ✅ |
| target_guard.py | Core | `FetchTargetGuard` — per-fetch SSRF policy shared by the HTTP and stealth tiers. `canonical_url` is the spelling a hop is judged and dialed in (`utils/url_syntax.py`; a URL with none is refused with `SSRFSecurityError`); `pin` judges it and returns the URL to request. Cloud policy: DNS-resolved, every address public. Local policy (`allow_private_networks`): the URL is judged, granted and resolved in canonical spelling (`pin` returns the URL as given) through `RedirectHopEvaluator.evaluate_hop_resolved` (a hostname resolving to loopback, link-local or metadata is judged as that address), the requested origin may be private, any other private origin reached by redirect may not, cloud metadata never may; skill DLP allowlist and `MYRM_ALLOWED_INTERNAL_HOSTS` apply under both. | ✅ |
| protocols.py | Core | Provides FetcherType, FetchResult (with optional raw_body for binary), Fetcher protocol. | ✅ |
| stealth_fetcher.py | Core | Stealth Fetcher — Maximum anti-detection based on Scrapling Patchright + BrowserForge. DNS leak prevention via DoH when proxy is active. Ad/tracker domain blocking via Scrapling `block_ads`. Scrapling navigates without a route hook, so the requested URL is judged before the browser starts and the page it ended on before the body is returned (`SSRFSecurityError` otherwise); the hop between them cannot be vetted in flight. | ✅ |
