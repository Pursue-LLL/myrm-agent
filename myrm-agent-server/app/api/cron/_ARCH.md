# api/cron/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Cron job REST API. | ✅ |
| `schemas.py` | 模块 | 定时任务 API 数据模型。定义 HTTP 请求/响应的 Pydantic schema， 提供字段校验（name 长度、retries 范围、monitor_type 枚举等）。 """ | ✅ |
