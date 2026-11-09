# router/

## Overview
Per-domain start-tier selection (the tier breaker) and the domain learning data web_fetch and the browser share (fetch failure history, SMART wait-strategy data, site experience)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Per-domain tier breaker and domain learning data | — |
| domain_metrics.py | Core | Domain-level learning metrics manager; saves and cleans up on a schedule as the store is used. | ✅ |
| models.py | Core | Domain learning data model (per-domain fetch failures, SMART wait-strategy data), its persisted JSON shape and the domain key. | ✅ |
| site_experience.py | Core | Site experience store with domain-level `prefer_http3` for L1 QUIC shortcut | ✅ |
| tier_breaker.py | Core | Per-domain tier breaker: a tier is skipped only after a higher tier made up for its failures three times; probed every tenth visit. | ✅ |

## Key Dependencies

- `infra`
