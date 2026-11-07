# services/migration/hermes 子目录

## 架构概述

`hermes/` 是迁移服务的 **Hermes 专用转换器聚合子目录**：把 Hermes 的 cron（`jobs.json`）转换为 Myrm CronJob，由上层 `migration` 服务按来源分派调用。MoA 预设不迁移（语义不兼容），导入后仅由 readiness 提示用户手动配置。

## 文件清单

| 文件 | 类型 | 职责 | 状态 |
| --- | --- | --- | --- |
| `__init__.py` | 门面 | 聚合导出 cron 转换/写入/回滚 API | ✅ |
| `hermes_cron_converter.py` | 核心 | Hermes `jobs.json` → Myrm CronJob 映射 + dry-run plan + skipped preview rows（无 model 字段，agent SSOT） | ✅ |
| `hermes_cron_migration.py` | 核心 | confirm 写入 CronManager（默认 paused，model=None）+ batch rollback | ✅ |

## 依赖边界

- 仅供迁移服务编排调用，不依赖业务层的渠道/定时任务运行时逻辑（转换产物由上层写库）。
- 无任何反向依赖：只读取 Hermes 配置文件结构，不修改用户源文件。
