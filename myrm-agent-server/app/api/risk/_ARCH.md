# api/risk/

## 架构概述

风险规则 CRUD 与实时检测 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Risk governance API module. | ✅ |
| `router.py` | 路由 | Risk governance API endpoints. | ✅ |
| `schemas.py` | 模块 | Risk governance API request/response schemas. | ✅ |
