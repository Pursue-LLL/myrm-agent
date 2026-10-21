# searxng/ 模块架构

## 架构概述

Bundled SearXNG instance config for local search (`myrm searxng` / docker-compose). Not application Python code — static files mounted into the SearXNG container.

## 文件清单

| 文件 | 职责 |
|------|------|
| `settings.yml` | SearXNG engine settings (languages, safe search, etc.) |
| `limiter.toml` | Rate limiting for the local instance |
| `uwsgi.ini` | uWSGI process config when running SearXNG standalone |

## 依赖

- Consumed by root `scripts/myrm` (`searxng` subcommand) and `myrm-agent-server/docker-compose.yaml` SearXNG service volume mounts.
- Frontend region presets: `myrm-agent-frontend/src/lib/search/searxngPresets.ts` (aligned with harness `SEARXNG_REGION_PRESETS`).
