# tunnel 模块架构

Cloudflare Quick Tunnel 进程生命周期（仅本地/WebUI 单机部署）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `manager.py` | 核心 | Quick Tunnel 启停、URL 解析（含 `parse_quick_tunnel_url_from_output`）、Ingress 快照恢复 | ✅ |
| `__init__.py` | 入口 | 导出 `get_tunnel_manager` | ✅ |

## 模块依赖

- `app.core.infra.ingress` — 运行时 Ingress URL
- `app.services.config.service` — `personalSettings.publicIngressBaseUrl` 持久化
- `app.config.deploy_mode` — SANDBOX 禁用 Quick Tunnel

## 约束

- SANDBOX 与已设置 `CP_PUBLIC_INGRESS_URL` 时禁止启动 Quick Tunnel
- 公网隧道启动前必须启用 WebUI 密码保护
