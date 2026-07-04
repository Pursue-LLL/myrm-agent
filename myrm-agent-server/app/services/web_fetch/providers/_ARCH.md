# providers/

## Overview

httpx implementations of harness `FetchEscalationProvider` for Jina Reader and Firecrawl scrape.

## Files

| File | Role | I/O/P |
|------|------|-------|
| jina.py | Jina Reader GET provider (optional API key, free tier default) | ✅ |
| firecrawl.py | Firecrawl v1 scrape POST provider (requires API key) | ✅ |

Both run `async_validate_url_for_ssrf` before outbound requests.
