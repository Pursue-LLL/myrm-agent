# cron/blueprints/core/

## 架构概述

蓝图核心：类型定义与纯函数（types.py）同注册/填充逻辑（registry.py）分离，前者不依赖任何蓝图数据。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出类型与注册表能力 | ✅ |
| `types.py` | 核心 | `CronBlueprint`/`BlueprintSlot` 等 dataclass、能力常量、时间→cron 与 locale 合并 | ✅ |
| `registry.py` | 核心 | 拼接内置清单、`get_blueprint`、`fill_blueprint` 与槽位校验 | ✅ |

## 依赖关系

- `registry.py` → `types.py`
