# maintain/

Wiki maintain 域子包 — 编排、schemas 与状态持久化。

## 架构概述

聚合 wiki maintain 管线：REST /maintain 与 Cron `__wiki_maintain__` 共用执行体（`runner`）、DTO（`schemas`）、UserConfig 上次维护状态持久化（`state_store`）。模块名 `app.services.wiki.maintain`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 runner/schemas/state_store 公开符号 | ✅ |
| `runner.py` | SSOT | `run_wiki_maintain_job` — POST /maintain?mode= 与 Cron `__wiki_maintain__` 共用；compile 进行中 skip；返回 lint issues + vault `reports/last-health.json` 快照 | ✅ |
| `schemas.py` | 类型 | `WikiMaintainState` / `WikiMaintainRunResult` / `WikiMaintainModeLiteral` | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiMaintainState` 上次维护 observability（按 agent） | ✅ |

## 依赖

- `app/services/wiki/_userconfig_scoped` — 共享 UserConfig scoped JSON 持久化（state_store 复用）
- `app.services.wiki.vault` — archiver / compile enqueue / health report
- `app.services.wiki.health_report_service` — `count_open_actions` (POS: vault health snapshot)
- `app.core.cron` — `__wiki_maintain__` router job
