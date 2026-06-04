# services/deploy 模块架构

---

## 架构概述

产物一键部署业务层。封装第三方托管平台 API（当前为 Vercel），负责静态/二进制文件打包、SPA 路由注入、部署状态轮询与网络重试。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `vercel_client.py` | ✅ 核心 | Vercel API v13：deploy（支持 projectId redeploy）、get_deployment_status |
| `deploy_packager.py` | ✅ 核心 | Vault 文件收集；`validate_deploy_payload` 校验 HTML 入口 |

---

## 依赖关系

- `httpx`：异步 HTTP 客户端
- `tenacity`：网络抖动重试
- 调用方：`app/api/files/deploy_api.py`

---

## Token 解析优先级（deploy_api）

1. 请求体 token
2. UserConfig 加密存储的用户 BYOK token
3. Sandbox 环境变量 `VERCEL_PLATFORM_TOKEN`（CP 注入）
