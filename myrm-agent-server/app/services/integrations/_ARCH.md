# services/integrations/

## 架构概述

集成服务业务编排层。将 Server DTO 转换为 Harness 能力调用，并在 API 层之前执行安全门禁。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `mcp_posture.py` | 核心 | MCP 静态/运行时安全姿态编排；posture block 抛结构化 `validation_error`（findings 在 error.details） |

## 依赖关系

- `myrm_agent_harness.toolkits.mcp.config_scan`：静态 + runtime surface MCP 扫描器
- `myrm_agent_harness.toolkits.mcp.security`：OSV 供应链检查
- `app/core/types.MCPServerConfig`：业务层 MCP 配置 DTO
