# services/hosting 模块架构

---

## 架构概述

Artifact 多目标发布业务层。封装 Vercel / Cloudflare Pages / Netlify / HTTP Webhook 托管 API，负责静态文件打包、SPA 路由注入、发布状态轮询与 SSRF 防护。**GUI Globe 发布专用，无 Agent 工具。**

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `orchestrator.py` | ✅ 核心 | `publish_artifact_to_target` — 预检、provider 调度、publication 持久化 |
| `registry.py` | ✅ 核心 | Provider 注册表 |
| `targets.py` | ✅ 核心 | UserConfig 中 hosting target CRUD |
| `credentials.py` | ✅ 核心 | 按 target 加密存储凭证 + legacy Vercel 迁移 |
| `publication_store.py` | ✅ 核心 | `artifact_publications` 表 CRUD |
| `packager.py` | ✅ 核心 | Vault 收集 + HTML 依赖解析 + 敏感目录排除 |
| `artifact_files.py` | ✅ 核心 | `resolve_artifact_deploy_files` — publish/share 共用 |
| `preflight.py` | ✅ 核心 | 发布前门禁 |
| `ssrf_guard.py` | ✅ 核心 | Webhook URL SSRF 校验 |
| `vercel_client.py` | ✅ 核心 | Vercel API v13 客户端 |
| `providers/*.py` | ✅ 核心 | 四平台 HostingProvider 实现 |

---

## 依赖关系

- `httpx`：异步 HTTP（webhook 禁用 follow_redirects）
- 调用方：`app/api/files/hosting_api.py`、`artifact_share_api.py`

---

## SSOT

- **唯一发布状态**：`artifact_publications`（UNIQUE artifact_id + hosting_target_id）
- API 响应区分 `provider_publication_ref`（平台 deployment id，WS 轮询用）与 `publication.id`（DB UUID）

---

## API

- `GET/POST/PUT/DELETE /artifacts/hosting/targets` — target CRUD
- `POST /artifacts/hosting/targets/{id}/make-default` — 事务性默认 target
- `POST /artifacts/{id}/publish` — 多目标发布
- `GET /artifacts/{id}/publications` — 各 target 发布状态
- `WS /artifacts/{id}/publish/status/{provider_publication_ref}` — 状态轮询

---

## Prompt Cache

不注册 LangChain deploy 工具；发布走 REST + GUI，零 LLM token。
