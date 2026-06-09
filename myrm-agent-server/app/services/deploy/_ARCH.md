# services/deploy 模块架构

---

## 架构概述

产物一键部署业务层。封装第三方托管平台 API（当前为 Vercel），负责静态/二进制文件打包、SPA 路由注入、部署状态轮询与网络重试。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `vercel_client.py` | ✅ 核心 | Vercel API v13：deploy（支持 projectId redeploy）、get_deployment_status |
| `deploy_packager.py` | ✅ 核心 | Vault 收集 + HTML 相对依赖解析（sandbox 同目录静态资源）+ 敏感目录排除；`validate_deploy_payload` |
| `artifact_files.py` | ✅ 核心 | `resolve_artifact_deploy_files(version_id=)` — deploy / share 共用的工件文件收集；share 路径传入 JWT claims 中的 `version_id` 精确定位版本，deploy 路径使用 latest |
| `preflight.py` | ✅ 核心 | `run_deploy_preflight` / `evaluate_deploy_preflight` — FE 部署前门禁 |
| `agent_deploy_service.py` | ✅ 核心 | `AgentDeployService` — 实现 harness `DeployBackend` Protocol，供 Agent 对话式部署 |

---

## 依赖关系

- `httpx`：异步 HTTP 客户端
- `tenacity`：网络抖动重试
- 调用方：`app/api/files/deploy_api.py`、`app/api/files/artifact_share_api.py`、`app/services/artifacts/share_bundle.py`、`app/ai_agents/general_agent/tool_setup.py`（Agent deploy tool）

---

## Token 解析优先级（deploy_api）

1. 请求体 token
2. UserConfig 加密存储的用户 BYOK token
3. Sandbox 环境变量 `VERCEL_PLATFORM_TOKEN`（CP 注入）
