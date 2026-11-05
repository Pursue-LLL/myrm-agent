# cron/blueprints/

## 架构概述

Cron 内置蓝图目录：`core/` 提供数据结构与注册/填充逻辑，`catalog/` 按主题分组存放 21 个蓝图定义，包根只保留门面与文档。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 对外导出 `BUILTIN_BLUEPRINTS`、`CronBlueprint`、`fill_blueprint` 等公开名字 | ✅ |
| `core/` | 子包 | 蓝图数据结构、能力常量、时间→cron 转换、注册表与填充校验 | ✅ |
| `catalog/` | 子包 | 按主题分组的蓝图数据，按声明顺序拼接成内置清单 | ✅ |

## 依赖

- `app.core.cron.blueprint_i18n_supplement` — ja/de/ko 文案补充
