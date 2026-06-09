# api/api_keys/

## 架构概述

API Key 签发与轮换 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | API Key management endpoints. | ✅ |
| `router.py` | 路由 | GUI-facing CRUD for managing API keys. | ✅ |
