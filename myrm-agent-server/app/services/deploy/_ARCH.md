# services/deploy 模块架构

---

## 架构概述

产物一键部署业务层。封装第三方托管平台 API（当前为 Vercel），负责静态/二进制文件打包、SPA 路由注入、部署状态轮询与网络重试。Agent 对话式部署工具与 GUI DeployModal 共用同一基础设施。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `vercel_client.py` | ✅ 核心 | Vercel API v13：deploy（支持 projectId redeploy）、get_deployment_status |
| `deploy_packager.py` | ✅ 核心 | Vault 收集 + HTML 相对依赖解析（sandbox 同目录静态资源）+ 敏感目录排除；`validate_deploy_payload` |
| `artifact_files.py` | ✅ 核心 | `resolve_artifact_deploy_files(version_id=)` — deploy / share 共用的工件文件收集 |
| `preflight.py` | ✅ 核心 | `run_deploy_preflight` / `evaluate_deploy_preflight` — FE 部署前门禁 |
| `types.py` | ✅ 核心 | `DeployResult` 数据类 |
| `protocols.py` | ✅ 核心 | `DeployBackend` Protocol |
| `deploy_agent_tools.py` | ✅ 核心 | `create_deploy_tool()` — LangChain `deploy_artifact` + HITL interrupt |
| `credentials.py` | ✅ 核心 | Vercel token 读写 SSOT：`save_vercel_credentials` / `resolve_vercel_token` |
| `vercel_artifact_deploy.py` | ✅ 核心 | `execute_vercel_artifact_deploy()` — REST + Agent 唯一执行入口 |
| `agent_deploy_service.py` | ✅ 核心 | `AgentDeployService` — `DeployBackend` 实现（委托 executor） |

---

## 依赖关系

- `httpx`：异步 HTTP 客户端
- `tenacity`：网络抖动重试
- 调用方：`app/api/files/deploy_api.py`、`app/api/files/artifact_share_api.py`、`app/ai_agents/general_agent/tool_setup.py`

---

## Token 解析优先级（credentials SSOT）

1. 请求体 token
2. UserConfig 加密存储的用户 BYOK token
3. Sandbox 环境变量 `VERCEL_PLATFORM_TOKEN`（CP 注入）

`deploy_api.py` POST 仅调 executor（单次 vault 读取）；GET preflight 仍用 `run_deploy_preflight` 服务 DeployModal。Token 读写均经 `credentials`。

---

## Agent 工具注册门控

`tool_setup._setup_deploy_tools()` 仅在 `has_deploy_credentials()` 为 True 时注册 deferred `deploy_artifact` 工具。
