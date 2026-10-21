# api/client_logs/

## 架构概述

客户端日志上报 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Client-side error logging endpoint. | ✅ |
