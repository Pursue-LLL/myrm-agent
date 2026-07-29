# onboarding/

## 架构概述

Server 层原子 onboarding 预设编排。复用 agent template 与 cron blueprint，不新增 harness meta-tools。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包 | 模块说明 | — |
| `second_brain_preset.py` | 核心 | Second Brain 预设：创建/复用 user agent + read_it_later cron + 4 项 checklist + rollback | ✅ |

## 依赖

- `app.api.agents.templates` — prebuilt agent 实例化与 skill enable
- `app.core.cron.blueprints` — `read_it_later` blueprint fill
- `app.services.config.service` — `secondBrainPreset` 状态持久化
- `app.api.config.router` — HTTP 暴露 `/onboarding/second-brain/{status,apply}`
