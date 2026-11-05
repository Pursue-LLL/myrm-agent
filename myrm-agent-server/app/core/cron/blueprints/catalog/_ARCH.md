# cron/blueprints/catalog/

## 架构概述

蓝图数据目录：四个主题模块各自导出 `BLUEPRINTS` 元组，由 `__init__.py` 按 daily → finance → knowledge → marketing 顺序导出；注册表再按同一顺序拼接，保证对外顺序稳定。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 汇总四个主题元组 | ✅ |
| `daily.py` | 数据 | 日常节奏蓝图（10 个） | ✅ |
| `finance.py` | 数据 | 金融监控与 SEO 周检蓝图 | ✅ |
| `knowledge.py` | 数据 | 稍后读与 wiki 系列蓝图 | ✅ |
| `marketing.py` | 数据 | 病毒式引语发现蓝图 | ✅ |
