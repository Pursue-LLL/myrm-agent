# web_fetch/

## Overview

Server-side **Web Fetch Escalation Layer (WFEL)** — L4 remote reader fallback (Jina / Firecrawl)
after harness CrawlEngine exhausts local L1 HTTP → L2 Browser → L3 Stealth. Default **OFF** via
Omni-Config `webFetchEscalation.enabled`. Vendor httpx calls live here; harness keeps Protocol only.

## File & Submodule Index

| File / Dir | Role | Description | I/O/P |
|------------|------|-------------|-------|
| binding.py | Core | Per agent-run ContextVar bind via `open_web_fetch_escalation_context` | ✅ |
| providers/jina.py | Core | Jina Reader httpx provider | ✅ |
| providers/firecrawl.py | Core | Firecrawl scrape httpx provider | ✅ |
| escalation/registry.py | Core | Build provider chain from config + searchServices inherit | ✅ |
| escalation/session_counter.py | Core | Per chat session L4 attempt cap | ✅ |
| escalation/_ARCH.md | Doc | Submodule index | ✅ |

## Wiring

- **Stream bind**: `app/ai_agents/general_agent/stream_pipeline.py` wraps agent run with
  `open_web_fetch_escalation_context(session_id, browser_source)`.
- **Verify API**: `app/api/integrations/web_fetch.py` POST `/integrations/web-fetch/verify`.
- **Config**: `app/schemas/config.py` → key `webFetchEscalation` (encrypted at rest).
- **Plane deny**: env `MYRM_WEB_FETCH_ESCALATION=denied` → registry returns no providers.

## Boundaries

- Harness: `FetchEscalationProvider` Protocol + ContextVar + `CrawlEngine._try_escalation`.
- Server: httpx vendors, user config, SSRF before outbound, session cap.
- **Not wired**: `mention.py` standalone `CrawlEngine()` — intentional lightweight @url prefetch.

## Dependencies

- `myrm_agent_harness.toolkits.web_fetch.escalation`
- `app.services.config.service`
- `app.schemas.config`
