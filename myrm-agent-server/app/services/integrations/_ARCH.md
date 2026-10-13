# services/integrations/

## 架构概述

集成服务业务编排层。将 Server DTO 转换为 Harness 能力调用，并在 API 层之前执行安全门禁。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `oauth_store.py` | 核心 | oauthCredentials 加密读写；`is_oauth_issuer_connected`；`google_workspace_write_enabled` / `google_drive_read_enabled`；共享 `oauth_credentials_lock` 串行化该 row 的跨写者 read-modify-write（refresh/upsert/delete）；`persist_credentials_locked` 为加密写回原语（upsert/delete/refresh merge 与 MCP OAuth 存储共用） |
| `retired_provider_oauth_purge.py` | 辅助 | 启动期一次性数据清理：`purge_retired_provider_credentials` 从 oauthCredentials 中移除已下线的 Claude / ChatGPT / GitHub Copilot 订阅登录遗留 issuer（`RETIRED_PROVIDER_ISSUERS`）；在共享行锁内读改写，无遗留 issuer 时不写回，无法解析的 blob 不覆盖；由 `server/lifespan.py` Phase 1a 在 DB 就绪后调用 |
| `mcp_posture.py` | 核心 | MCP 静态/运行时安全姿态编排；posture block 抛结构化 `validation_error`（findings 在 error.details） |
| `mcp_registry.py` | 核心 | MCP 注册中心代理服务；搜索/详情代理 Smithery Registry，LRU 缓存，异步 httpx |
| `search_verify.py` | 核心 | 统一搜索 provider 验证服务；`verify_search_config_live` 基于 catalog manifest SSOT 过滤 + live probe 执行 + 60s TTL 缓存 |

## 依赖关系

- `myrm_agent_harness.toolkits.mcp.config_scan`：静态 + runtime surface MCP 扫描器
- `myrm_agent_harness.toolkits.mcp.security`：OSV 供应链检查
- `app/core/types.MCPServerConfig`：业务层 MCP 配置 DTO
- `httpx`：异步 HTTP 客户端（mcp_registry 用于外部 API 调用）
