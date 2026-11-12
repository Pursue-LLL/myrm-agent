# web_fetch/

## Overview

Layered single-page web fetch engine with L1 HTTP / L2 Browser / L3 Stealth fallback, per-domain start-tier breaker, optional L4 remote escalation, and full-content delivery that shortens long pages to one shared budget while saving the complete text for `file_read_tool`.

## Submodule Index

| Submodule | Role | Description |
|-----------|------|-------------|
| [engine/](engine/_ARCH.md) | Core | FetchEngine tiered fetcher pool |
| [processing/](processing/_ARCH.md) | Core | Post-fetch pipeline, markdown, full-content delivery, anti-bot |
| [probe/](probe/_ARCH.md) | Util | HTTP/3 probe and charset detection |
| [extractors/](extractors/_ARCH.md) | Core | WeChat / Bilibili / YouTube / X fast-paths |
| [fetchers/](fetchers/_ARCH.md) | Core | L1/L2/L3 fetcher implementations |
| [router/](router/_ARCH.md) | Core | Per-domain tier breaker and domain learning data |
| [escalation/](escalation/_ARCH.md) | Core | L4 remote fetch hook |

## Package Root Files (facade only)

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports FetchEngine and result types | ✅ |
| web_fetch_agent_tools.py | Core | LangChain web_fetch_tool factory; with both embedding and reranker configs the tool offers `fetch_and_extract` and `fetch_full_content`, otherwise it only reads pages in full (`urls`, up to 5, plus `reason`; all pages share one budget, the complete text is saved when any page is cut, and a page whose source hit the fetch size ceiling is named by number in a notice after the untrusted block); every URL passes `_url_gate.validate_urls` first and the tool fetches the canonical spelling it returns; the pages of a full read are labelled with the run's source numbers (`source_indexer_var`), so each label is the index of its source card | ✅ |
| _web_fetch_tool_description.py | Core | LLM-visible tool description SSOT (EN/ZH); names the readable document formats (PDF, DOCX, XLSX, PPTX) and never mentions browser tools | ✅ |
| _url_gate.py | Core | `validate_urls` — the gate every URL of a `web_fetch_tool` call passes before any request: each URL is parsed into its canonical spelling (`utils/url_syntax.py`, a URL with none is refused) and returned in it, so the host judged is the host fetched. The benchmark hostname blocklist runs on the canonical host; the cloud policy (not `allow_private_networks`) adds the SSRF classification and the secret-in-URL check on the same spelling | ✅ |

## L4 Escalation (WFEL)

After local L1-L3 failure, `FetchEngine._try_escalation` tries injected `FetchEscalationProvider`
chain (Jina then Firecrawl when enabled in server config). Providers bind per agent run via
`escalation/context.py` ContextVar — **not** global singleton mutation.

- L2 Browser respects `get_bound_browser_launch_mode()` for extension CDP pages.

## Tool routing (web_fetch vs browser)

When both tools are mounted: read-only pages → `web_fetch_tool` (CORE); interactive flows → browser tools (EXTENDED). Guidance lives in the Dynamic Hint on `browser_navigate_tool` (`browser/tools/navigate.py`), not System Prompt; the Schema Weaver drops it when `web_fetch_tool` is not mounted, and the `web_fetch_tool` description never mentions browser tools, so it stays correct when none is mounted. Loop Guard provides symmetric fallback suggestions. See `toolkits/browser/BROWSER_SYSTEM.md` §web_fetch 与 browser 分工.

## Key Dependencies

- `toolkits.retriever` (for fetch_and_extract mode)
- `httpx`
- `[web]` optional: `scrapling`, `curl_cffi` (L1 bounded download), `youtube-transcript-api`
