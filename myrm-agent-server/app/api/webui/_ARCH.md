# api/webui/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WebUI 相关 API | ✅ |
| `auth_routes.py` | 路由 | WebUI 浏览器认证 HTTP 入口（setup/login/status/logout/token-exchange）。 """ | ✅ |
| `router.py` | 路由 | WebUI API 路由 | ✅ |
