# api/webui/

## 架构概述

WebUI 浏览器认证 HTTP 层：setup/login/logout/session + VNC 可视化桌面控制。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WebUI 相关 API | ✅ |
| `auth_routes.py` | 路由 | WebUI 浏览器认证 HTTP 入口（setup/login/status/logout/token-exchange）。 | ✅ |
| `device_routes.py` | 路由 | WebUI 移动端设备交互 HTTP 入口（`/device/doctor`、`/device/snapshot`、`/device/relay`），委托 `services.device.bridge_service`。 | ✅ |
| `router.py` | 路由 | WebUI API 聚合路由（挂载 auth + vnc + device 子路由；`/desktop/permissions` 临时 probe 后 `session.close()`；`/desktop/screen-lock/status` 物理锁屏休眠门禁状态探测） | ✅ |
| `vnc_routes.py` | 路由 | VNC 可视化桌面 API（status/start/stop/takeover/resume），本地模式 VNC 服务控制。`/takeover` 不依赖 VNC 可用：`GET` 读取接管状态，`POST` 接管并在已接管时续租（客户端心跳），`/resume` 交还；TakeoverCoordinator 的状态变化经 `on_state_change` 映射到进程级 `UserControl`，接管期间 Agent 的浏览器/桌面工具等待，交还后动作须先重新观察。注册 TakeoverCoordinator 生命周期钩子，在接管前后自动拍摄 ARIA 页面快照并写入 `takeover_trace` 事件至 EventLog。 | ✅ |
