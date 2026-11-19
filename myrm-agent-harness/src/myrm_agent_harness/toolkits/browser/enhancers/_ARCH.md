# enhancers/

## Overview
DOM enhancer for the browser toolkit: the script every pooled context registers as an init script (`pool/context_factory.py`), so the browser runs it in every document of the context before the page's own scripts.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Re-exports `get_dom_enhancer_script`. | — |
| `dom_enhancer_loader.py` | Core | Loads and caches the DOM enhancement JavaScript that the context factory registers as an init script. A page whose `script-src` policy forbids inline script still receives it (pinned by `tests/toolkits/browser/test_post_action_settle_integration.py`). | ✅ |
| `dom_enhancer.js` | Resource | The script every pool-created context delivers into its pages: React fiber hook, interactive-element registry, and the SPA tracker `window.__myrm_spa_state`. The tracker numbers every fetch/XHR (`requestSeq`; in-flight ids in `pending`; `lastRequestEnd`), leaves out fetches whose URL path has a noise segment (ping, heartbeat, analytics, metrics, track, log, ws, socket, socket.io; whole segments only, so `/login` and `/tracking` are tracked; XHR is always tracked), and marks where each user gesture began (`gestureSeq`, `gestureTime`: the first input event after 400 ms without one). Consumers: `wait/_action_settle.py` (the requests an interaction waits for) and the SPA-stable probe in `wait/_impl.py` (`inflightRequests`, `stable`). Initialised once per window. | — |

## Key Dependencies

- Standard library only; `pool/context_factory.py` is the consumer that registers the script.
