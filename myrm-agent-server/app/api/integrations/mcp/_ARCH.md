# api/integrations/mcp/

## 架构概述

MCP 服务器的检查类 HTTP 端点：选项查询、静态扫描、连接验证、UI 资源读取，以及并入同一路由的 Registry 搜索 / 详情代理与本地连通性探测。`inspection.py` 持有包的 `router`，把 `resource.py` 与 `probe_registry.py` 的子路由并进来，由 [../router.py](../router.py) 挂在 `/integrations/mcp` 下；授权码 + PKCE 的 OAuth 端点在 [../oauth/_ARCH.md](../oauth/_ARCH.md)。上级文档：[../_ARCH.md](../_ARCH.md)。

## 路由

| 路径（相对 `/integrations/mcp`） | 方法 | 定义位置 |
|------|------|------|
| `/options` | GET | `inspection.py` |
| `/scan` | POST | `inspection.py` |
| `/scan-batch` | POST | `inspection.py` |
| `/verify` | POST | `inspection.py` |
| `/resource` | GET | `resource.py` |
| `/registry/search` | GET | `probe_registry.py` |
| `/registry/detail/{qualified_name}` | GET | `probe_registry.py` |
| `/probe` | POST | `probe_registry.py` |

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 `router` | ✅ |
| `inspection.py` | 模块 | `/verify` 单次握手同时完成工具枚举与 `instructions` 提取（零二次进程派生）；`/scan` 与 `/scan-batch` 做不联网的静态预检；`/options` 返回部署形态允许的传输方式；末尾把 `resource` 与 `probe_registry` 的路由并入同一个 `router`。 | ✅ |
| `schemas.py` | 模块 | verify / scan 的响应模型（`MCPVerifyData` / `MCPScanData` / `MCPToolDetail` / `MCPScanFindingData`）与 `scan_result_to_data`（扫描最高严重度按风险序而非标签字典序）。 | ✅ |
| `resource.py` | 模块 | `/resource`：经已打开的连接读取 MCP App 的 UI 资源并以 base64 返回，MIME 按 URI 后缀判定；逐个连接尝试，全部失败时报告最后一个原因。 | ✅ |
| `probe_registry.py` | 模块 | Registry 搜索 / 详情代理与本地连通性探测 `/probe`（返回 `reason_code` / `recommended_mode` / `should_block_connect` 结构化语义，支持 cloud loopback guard UX）。 | ✅ |
