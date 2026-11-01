# browser/wait/

## Overview

Page wait strategies — hybrid detection for optimal page ready detection. Four strategies (smart/hybrid/dom_stable/networkidle) with runtime statistics, domain-level learning, and full metrics.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public facade: `wait_for_page_ready` (runs one strategy attempt and re-arms it on the new document when a navigation destroys the probe's document, within the remaining budget), `WaitStrategy`, `WaitMetrics`, `WaitStrategyStats`, global stats accessors | ✅ |
| `_impl.py` | Core | 4 strategy implementations (networkidle/dom_stable/smart/hybrid) + SPA stable; `is_navigation_interrupt` recognises patchright's bare "Execution context was destroyed" error; SMART skips the fast path only when `DomainMetrics.should_skip_smart_fast_path()` (≥20 networkidle samples, success rate < 50%); `wait_hybrid` cancels both probe tasks on any escaping error | ✅ |
| `_types.py` | Config | Type definitions: `WaitStrategy`/`WaitMetrics`/`WaitStrategyStats` + thread-safe runtime stats | ✅ |
| `_dom_stable_js.py` | Resource | DOM stability detection JavaScript generator (MutationObserver incl. Shadow DOM) | ✅ |

## Key Dependencies

- `toolkits/web_fetch/router/domain_metrics` (domain-level metric recording, optional)
- `patchright.async_api::Page`
