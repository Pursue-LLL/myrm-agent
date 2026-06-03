# api/webui 模块架构


---

## 架构概述

WebUI 辅助接口，挂载在 app 根路由（不在 `/api/v1` 下），提供认证状态查询、二维码和欢迎页。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `router.py` | ✅ 核心 | WebUI 辅助接口：二维码、欢迎页、Inspector；挂载 auth 子路由。 |
| `auth_routes.py` | ✅ 核心 | `/webui/auth/*` setup/login/logout/token-exchange/status |
| `__init__.py` | ✅ 包标记 | 仅暴露 `router`。 |

---

## 路由挂载

webui_router 直接挂在 FastAPI `app` 根路由上（`main.py`），不在 `api_router`（`/api/v1`）下。
前端通过 `BACKEND_BASE_URL`（`http://localhost:8080`）直接访问。

---

## 公开端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/webui/auth/status` | GET | 本地/远程 WebUI 认证状态（Remote 未 setup 时 `is_setup_done=false`） |
| `/webui/auth/setup` | POST | 首次设置 admin 密码（需 temp_token） |
| `/webui/auth/login` | POST | admin 登录，设置 httpOnly 会话 Cookie |
| `/webui/auth/logout` | POST | 清除会话 Cookie |
| `/webui/auth/token-exchange` | POST | URL 中 temp_token 换会话 |
| `/webui/auth/protection` | GET/PUT | 读取/更新密码保护开关 |
| `/webui/auth/change-password` | POST | 修改 admin 密码 |
| `/webui/auth/disable-protection` | POST | 验证密码后关闭保护 |
| `/webui/auth/generate-setup-token` | POST | 生成首次设置或轮换链接 |
| `/webui/qrcode.png` | GET | 生成 WebUI 访问二维码。 |
| `/webui/welcome` | GET | 生成欢迎页，展示访问地址和二维码。 |
| `/webui/browser/snapshot` | GET | 获取当前浏览器截图 + ARIA refs + BBox 数据，供 Browser Inspector 使用。 |
| `/webui/desktop/snapshot` | GET | 获取当前桌面截图 + AX @dref refs + BBox 数据，供 Desktop Inspector 使用。 |

---

## 依赖关系

- `app/services/webui/qrcode.py`：二维码和 URL 组装
- `app.config.settings`：WebUI 端口、二维码尺寸
- `myrm_agent_harness.utils.get_local_ip`：本机 IP 解析
- `app/services/agent/gateway.py`：AgentGateway 单例（Browser/Desktop Inspector 通过弱引用获取活跃 Session）
- `myrm_agent_harness.toolkits.browser.session`：BrowserSession + SnapshotResult（Browser Inspector snapshot API）
- `myrm_agent_harness.toolkits.computer_use.desktop_session`：DesktopSession + export_inspector_snapshot（Desktop Inspector snapshot API）
