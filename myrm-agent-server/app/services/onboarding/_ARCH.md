# onboarding/

## 架构概述

Server 层原子 onboarding 预设编排。复用 agent template 与 cron blueprint，不新增 harness meta-tools。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包 | 模块说明 | — |
| `schemas.py` | SSOT | Second Brain preset Pydantic models | — |
| `second_brain_preset.py` | 核心 | Second Brain 预设：创建/复用 user agent + default→agent vault seed（新建或复用 agent 均触发）+ read_it_later + wiki_morning_delta 双 cron + 4 项 checklist + rollback；apply 成功 message 含 vault seed 计数；status 发现 agent 已删则清 `secondBrainPreset` | ✅ |

## 依赖

- `app.api.agents.templates` — prebuilt agent 实例化与 skill enable
- `app.core.cron.blueprints` — `read_it_later` blueprint fill
- `app.services.config.service` — `secondBrainPreset` 状态持久化
- `app.services.wiki.vault_resolver` — `seed_agent_vault_from_default` + checklist vault probe
- `app.api.config.router` — HTTP 暴露 `/onboarding/second-brain/{status,apply}`
