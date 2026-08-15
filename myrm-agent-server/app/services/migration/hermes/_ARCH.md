# services/migration/hermes 子目录

## 架构概述

`hermes/` 是迁移服务的 **Hermes 专用转换器聚合子目录**：把 Hermes 的 cron（`jobs.json`）与 MOA preset 配置转换为 Myrm 的 CronJob 与 Agent 引擎参数，由上层 `migration` 服务按来源分派调用。

## 文件清单

| 文件 | 类型 | 职责 | 状态 |
| --- | --- | --- | --- |
| `hermes_cron_converter.py` | 核心 | Hermes `jobs.json` → Myrm CronJob 映射 + dry-run plan + skipped preview rows（无 model 字段，agent SSOT） | ✅ |
| `hermes_cron_migration.py` | 核心 | confirm 写入 CronManager（默认 paused，model=None）+ batch rollback | ✅ |
| `hermes_moa_migrator.py` | 辅助 | Hermes `moa.presets` → 目标 Agent `engine_params.moa_overlay`（ref 模型 + fanout/隐私参数；不迁移 aggregator） | ✅ |

## 依赖边界

- 仅供迁移服务编排调用，不依赖业务层的渠道/定时任务运行时逻辑（转换产物由上层写库）。
- 无任何反向依赖：只读取 Hermes 配置文件结构，不修改用户源文件。
