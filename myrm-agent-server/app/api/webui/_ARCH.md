# api/webui/

## 架构概述

WebUI 浏览器认证 HTTP 层：setup/login/logout/session + VNC 可视化桌面控制。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WebUI 相关 API | ✅ |
| `auth_routes.py` | 路由 | WebUI 浏览器认证 HTTP 入口（setup/login/status/logout/token-exchange）。 | ✅ |
| `router.py` | 路由 | WebUI API 路由（含 auth + vnc 子路由） | ✅ |
| `vnc_routes.py` | 路由 | VNC 可视化桌面 API（status/start/stop/takeover/resume），本地模式 VNC 服务控制。 | ✅ |
