# api/system/

## 架构概述

系统信息、版本、存储优化与受控关机 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | System API routes. | ✅ |
| `router.py` | 路由 | Ingress 需求/URL、LAN 网络信息、存储磁盘信息与会话数据库智能优化（预检/FTS optimize/VACUUM/WAL truncate）、沙箱容器重建（SaaS）、支持排障包与全量资产 Takeout 导出 | ✅ |
| `schemas.py` | 数据结构 | System API 请求、响应与存储治理数据传输模型 (Pydantic) | ✅ |
| `shutdown.py` | 模块 | HTTP shutdown/drain control — `POST /shutdown` (graceful SIGTERM), `POST /drain` (begin draining), `DELETE /drain` (cancel drain). | ✅ |
