# api/webui/

## 架构概述

WebUI 浏览器认证 HTTP 层：setup/login/logout/session + VNC 可视化桌面控制。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WebUI 相关 API | ✅ |
| `auth_routes.py` | 路由 | WebUI 浏览器认证 HTTP 入口（setup/login/status/logout/token-exchange）。 | ✅ |
| `router.py` | 路由 | WebUI API 聚合路由（挂载 auth、vnc、desktop 三个子路由；自带 og-metadata 代理、二维码、`/welcome`、浏览器快照；`/welcome` 的页面交给 `welcome_page.py`；`host` 查询参数只接受主机名 / IP 字面量字符，因为免登录的 `/welcome` 把它写进 HTML 与脚本） | ✅ |
| `desktop_routes.py` | 路由 | 桌面面板 API（`/webui/desktop/*`）：`/permissions` 临时 probe 后 `session.close()`，`/screen-lock/status` 物理锁屏休眠门禁状态探测，`/snapshot` 三种来源，`/approval/*`（待批列表、处理、重置、仅本地的 `test-seed`，隐藏于 OpenAPI，非本地 404），`/trust/apps`，`/envelope/*`；harness 与 desktop_control 模块在处理函数内延迟导入，没装 computer-use 依赖也能启动；测试 patch 的是源模块，不是本文件 | ✅ |
| `welcome_page.py` | 页面 | 局域网启动欢迎页（`render_welcome_page(host, port)`）：二维码地址按所在位置分别编码（属性转义、脚本 JSON 字符串、可见文字转义）；颜色一律写在样式表里并满足对比度，按钮有聚焦环；`tests/api/webui/test_welcome_page.py` 钉住 | ✅ |
| `vnc_routes.py` | 路由 | VNC 可视化桌面 API（status/start/stop/takeover/resume），本地模式 VNC 服务控制。`/takeover` 不依赖 VNC 可用：`GET` 读取接管状态，`POST` 接管并在已接管时续租（客户端心跳），`/resume` 交还；TakeoverCoordinator 的状态变化经 `on_state_change` 映射到进程级 `UserControl`，接管期间 Agent 的浏览器/桌面工具等待，交还后动作须先重新观察。注册 TakeoverCoordinator 生命周期钩子，在接管前后自动拍摄 ARIA 页面快照并写入 `takeover_trace` 事件至 EventLog。该事件直接 `append` 到后端、不经过会脱敏的 `EventLogger`，所以页面状态（前后 URL、ARIA 树）写入前经 harness `sanitize_event_data`；ARIA 树多读 1000 字符再截到 3000，跨过截断点的凭据整条遮蔽。 | ✅ |
