# api/integrations/

## 架构概述

集成目录、OAuth 凭证与 Hardware Cookbook HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External integrations API module | ✅ |
| `catalog.py` | 模块 | Integration Catalog API endpoints；透传 registry 归一化后的显式 `deployment_scope`（`local_tauri_only` / `all_modes`），透传 `post_connect_guide`。 | ✅ |
| `hardware.py` | 模块 | 硬件推荐 API：检测本地硬件、估算 Tokens/s 并生成 Ollama 模型适配度推荐，含 Ollama pull/delete 代理端点。 | ✅ |
| `im_contacts.py` | 模块 | Lightweight search users API for IM group management. | ✅ |
| `integration_memory.py` | 模块 | REST API layer for Integration Memory. | ✅ |
| `llms.py` | 模块 | LLM 验证 / 可达性检查 / OpenAI-compatible `discover-models`（SSRF 保护 + local/tauri loopback allowlist，支持 loopback no-auth 与 loopback+key） | ✅ |
| `mcp.py` | 模块 | MCP verify/scan/probe API；`/probe` 返回 `reason_code/recommended_mode/should_block_connect` 结构化语义（含 `tls_verification_failed`），支持 cloud loopback guard UX。 | ✅ |
| `google_workspace_oauth.py` | 模块 | Google Workspace OAuth 2.0 + PKCE；readonly/write tier；写入 oauthCredentials（不含 client_secret） | ✅ |
| `google_workspace_oauth_flow.py` | 模块 | OAuth PKCE 会话态、scope tier、redirect 解析与 Google userinfo 辅助 | ✅ |
| `mcp_oauth.py` | 模块 | MCP OAuth 2.0 + PKCE authorization flow API. | ✅ |
| `model_specs.py` | 模块 | Settings Hardware Cookbook 使用的 Ollama 模型规格数据源。 | ✅ |
| `oauth.py` | 模块 | OAuth 凭证管理 API。提供个人 SaaS 集成凭证的加密存储、查询和撤销，支持断开时可选清除同步数据。 | ✅ |
| `retrieval.py` | 模块 | Retrieval Service Configuration Validation API | ✅ |
| `router.py` | 路由 | Integrations API router | ✅ |
| `search.py` | 模块 | 搜索引擎验证请求模型 | ✅ |
