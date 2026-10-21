# escalation/

## Overview

Build ordered L4 provider chain (Jina → Firecrawl) from Omni-Config and optional searchServices
Firecrawl key inherit. Applies per-session attempt cap via `SessionEscalationCounter`.

## Files

| File | Role | I/O/P |
|------|------|-------|
| registry.py | Provider chain builder + env deny + Firecrawl key resolve | ✅ |
| session_counter.py | Thread-safe session cap counter | ✅ |

## Dependencies

- `app/schemas/config`
- `app/services/web_fetch/providers/`
