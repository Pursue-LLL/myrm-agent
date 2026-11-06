# onboarding/

## 架构概述

Server 层原子 onboarding 预设编排。复用 agent template 与 cron blueprint，不新增 harness meta-tools。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包 | 模块说明 | — |
| `schemas.py` | SSOT | Second Brain preset Pydantic models | — |
| `second_brain_preset/` | 核心 | Second Brain 预设，按读写路径与 cron 供给拆 7 个模块（common / checks / cron_setup / job_repair / mutations / status / apply）：创建/复用 user agent + vault seed、read-it-later + wiki delta + maintenance cron、4 项 checklist、幂等 apply 与失败回滚、启动期 wiki-delta 声明修复；`get_cron_manager` 收敛到 `common` 作为唯一打桩点。见 [second_brain_preset/_ARCH.md](second_brain_preset/_ARCH.md) | ✅ |

## 依赖

- `app.api.agents.templates` — prebuilt agent 实例化与 skill enable
- `app.core.cron.blueprints` — `read_it_later` blueprint fill
- `app.services.config.service` — `secondBrainPreset` 状态持久化
- `app.services.wiki.vault` — `seed_agent_vault_from_default` + checklist vault probe
- `app.api.config.router` — HTTP 暴露 `/onboarding/second-brain/{status,apply}`
