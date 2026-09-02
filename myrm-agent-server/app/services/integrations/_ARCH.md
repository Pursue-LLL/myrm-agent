# services/integrations/

## 架构概述

集成服务业务编排层。将 Server DTO 转换为 Harness 能力调用，并在 API 层之前执行安全门禁。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `oauth_store.py` | 核心 | oauthCredentials 加密读写；`is_oauth_issuer_connected`；`google_workspace_write_enabled` / `google_drive_read_enabled`；`extract_copilot_base_url`（Copilot token base URL 解析共享函数）；共享 `oauth_credentials_lock` 串行化该 row 的跨写者 read-modify-write（refresh/upsert/delete）；`persist_credentials_locked` 为加密写回原语（upsert/delete/refresh merge 与 MCP OAuth 存储共用） |
| `mcp_posture.py` | 核心 | MCP 静态/运行时安全姿态编排；posture block 抛结构化 `validation_error`（findings 在 error.details） |
| `mcp_registry.py` | 核心 | MCP 注册中心代理服务；搜索/详情代理 Smithery Registry，LRU 缓存，异步 httpx |
| `search_verify.py` | 核心 | 统一搜索 provider 验证服务；`verify_search_config_live` 基于 catalog manifest SSOT 过滤 + live probe 执行 + 60s TTL 缓存 |

## 依赖关系

- `myrm_agent_harness.toolkits.mcp.config_scan`：静态 + runtime surface MCP 扫描器
- `myrm_agent_harness.toolkits.mcp.security`：OSV 供应链检查
- `app/core/types.MCPServerConfig`：业务层 MCP 配置 DTO
- `httpx`：异步 HTTP 客户端（mcp_registry 用于外部 API 调用）
