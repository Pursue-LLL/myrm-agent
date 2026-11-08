# browser/wait/

## Overview

Page wait strategies — hybrid detection for optimal page ready detection. Four strategies (smart/hybrid/dom_stable/networkidle) with runtime statistics, domain-level learning, and full metrics. Also the wait an interaction ends with (`settle_after_action`), which is not a readiness strategy: it waits for the requests the action itself started.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public facade: `wait_for_page_ready` (runs one strategy attempt and re-arms it on the new document when a navigation destroys the probe's document, within the remaining budget), `WaitStrategy`, `WaitMetrics`, `WaitStrategyStats`, `settle_after_action`, `capped_note`, global stats accessors | ✅ |
| `_impl.py` | Core | 4 strategy implementations (networkidle/dom_stable/smart/hybrid) + SPA stable; `is_navigation_interrupt` recognises patchright's bare "Execution context was destroyed" error; SMART skips the fast path only when `DomainMetrics.should_skip_smart_fast_path()` (≥20 networkidle samples, success rate < 50%); `wait_hybrid` cancels both probe tasks on any escaping error | ✅ |
| `_action_settle.py` | Core | `settle_after_action(target, cap_ms=3000)` — what an interaction ends with, whatever the action except one that only moves the pointer, the focus or the viewport. Runs in the page, or in the frame of the iframe the action's element is in, because every document has its own tracker. Reads the page-side tracker (`window.__myrm_spa_state` in the main world, written by `enhancers/dom_enhancer.js`): waits for the fetch/XHR requests numbered after the start of the user gesture to finish (requests already in flight, beacons and long-lived channels are not the action's and are ignored), then gives the page a short draw window. Returns why it ended (`settled` / `no_request` / `untracked` / `capped` / `failed`) and never raises except on cancellation: a document without the tracker, an action that sent no input, or a page that goes away mid-wait leave the page as the action left it. `capped_note(outcome)` is the sentence an answer ends with when the wait ended at its cap. Independent of `WaitStrategy`: navigation keeps using `wait_for_page_ready`. | ✅ |
| `_types.py` | Config | Type definitions: `WaitStrategy`/`WaitMetrics`/`WaitStrategyStats` + thread-safe runtime stats | ✅ |
| `_dom_stable_js.py` | Resource | DOM stability detection JavaScript generator (MutationObserver incl. Shadow DOM) | ✅ |

## Key Dependencies

- `toolkits/web_fetch/router/domain_metrics` (domain-level metric recording, optional)
- `patchright.async_api::Page`
