# services/integrations/

## 架构概述

集成服务业务编排层。将 Server DTO 转换为 Harness 能力调用，并在 API 层之前执行安全门禁。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `oauth_store.py` | 核心 | oauthCredentials 加密读写；`is_oauth_issuer_connected` 探测 issuer 是否已存 token |
| `mcp_posture.py` | 核心 | MCP 静态/运行时安全姿态编排；posture block 抛结构化 `validation_error`（findings 在 error.details） |
| `mcp_registry.py` | 核心 | MCP 注册中心代理服务；搜索/详情代理 Smithery Registry，LRU 缓存，异步 httpx |

## 依赖关系

- `myrm_agent_harness.toolkits.mcp.config_scan`：静态 + runtime surface MCP 扫描器
- `myrm_agent_harness.toolkits.mcp.security`：OSV 供应链检查
- `app/core/types.MCPServerConfig`：业务层 MCP 配置 DTO
- `httpx`：异步 HTTP 客户端（mcp_registry 用于外部 API 调用）
