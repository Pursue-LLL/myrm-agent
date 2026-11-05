# api/cron/

## 架构概述

Cron 任务 CRUD 与运行记录 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST API. | ✅ |
| `schemas/` | 子包 | 定时任务 API 数据模型，按区域分 5 个模块（delivery / triggers / jobs / usage / operations），`__init__` 聚合 41 个 schema；校验规则（name 长度、retries 范围、monitor_type 枚举等）随字段保留。见 [schemas/_ARCH.md](schemas/_ARCH.md) | ✅ |
