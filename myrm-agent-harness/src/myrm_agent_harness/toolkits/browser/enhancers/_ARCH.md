# enhancers/

## Overview
DOM enhancers for the browser toolkit. Injects JavaScript to improve page readability and accessibility.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Re-exports `get_dom_enhancer_script` and `install_document_script_injection`. | — |
| `dom_enhancer_loader.py` | Core | Loads and caches DOM enhancement JavaScript for injection into browser pages. | ✅ |
| `dom_enhancer.js` | Resource | The script every pool-created context delivers into its pages: React fiber hook, interactive-element registry, and the SPA tracker `window.__myrm_spa_state`. The tracker numbers every fetch/XHR (`requestSeq`; in-flight ids in `pending`; `lastRequestEnd`), leaves out fetches whose URL path has a noise segment (ping, heartbeat, analytics, metrics, track, log, ws, socket, socket.io; whole segments only, so `/login` and `/tracking` are tracked; XHR is always tracked), and marks where each user gesture began (`gestureSeq`, `gestureTime`: the first input event after 400 ms without one). Consumers: `wait/_action_settle.py` (the requests an interaction waits for) and the SPA-stable probe in `wait/_impl.py` (`inflightRequests`, `stable`). Initialised once per window. | — |
| `inject_route.py` | Core | `install_document_script_injection` — per-context document-response rewrite (`route.fulfill`) that prepends `<script>` tags to every HTML page; the reliable script-delivery path under patchright where `add_init_script` silently no-ops. One route handler serves ALL registered scripts (fulfill terminates the route chain, so multiple handlers would be mutually exclusive). The handler is transparent to everything it does not rewrite: it fetches with `max_redirects=0` and hands 3xx, non-HTML, empty and undecodable responses back to Chromium unchanged via `route.fulfill(response=…)`, so Chromium performs the redirect itself (correct page URL and origin, cookies, `redirected_from` chain visible to the SSRF checks) and no document is requested twice; a non-idempotent request (form POST) is fetched with the driver timeout lifted and, if the route fails, aborted instead of handed back — so a slow write endpoint is never submitted a second time; script sources are escaped against `</script>` breakouts; charset-aware decode/encode keeps legacy-charset pages intact; undecodable bodies fall through untouched; a page whose `script-src` policy forbids inline script still receives the scripts (pinned by `tests/toolkits/browser/test_post_action_settle_integration.py`). | ✅ |

## Key Dependencies

- patchright.async_api (BrowserContext, Route)
- pool.stealth (stealth.js consumer of inject_route)