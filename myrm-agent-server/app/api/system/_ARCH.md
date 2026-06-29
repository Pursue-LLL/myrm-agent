# api/system/

## 架构概述

系统信息、版本与受控关机 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | System API routes. | ✅ |
| `router.py` | 路由 | Ingress 需求/URL、LAN 网络信息、存储磁盘信息 | ✅ |
| `shutdown.py` | 模块 | HTTP shutdown control. | ✅ |
