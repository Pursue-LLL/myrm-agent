# api/integrations/

## 架构概述

集成目录、OAuth 凭证与 Hardware Cookbook HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External integrations API module | ✅ |
| `catalog.py` | 模块 | Integration Catalog API endpoints. | ✅ |
| `hardware.py` | 模块 | 获取硬件探针结果（带内存缓存，避免阻塞事件循环） | ✅ |
| `im_contacts.py` | 模块 | Lightweight search users API for IM group management. | ✅ |
| `integration_memory.py` | 模块 | REST API layer for Integration Memory. | ✅ |
| `llms.py` | 模块 | LLM验证请求模型 | ✅ |
| `mcp.py` | 模块 | 获取 MCP Agent 实例（单例模式） | ✅ |
| `mcp_oauth.py` | 模块 | MCP OAuth 2.0 + PKCE authorization flow API. | ✅ |
| `model_specs.py` | 模块 | Settings Hardware Cookbook 使用的 Ollama 模型规格数据源。 | ✅ |
| `oauth.py` | 模块 | OAuth 凭证管理 API。提供个人 SaaS 集成凭证的加密存储、查询和撤销，支持断开时可选清除同步数据。 | ✅ |
| `retrieval.py` | 模块 | Retrieval Service Configuration Validation API | ✅ |
| `router.py` | 路由 | Integrations API router | ✅ |
| `search.py` | 模块 | 搜索引擎验证请求模型 | ✅ |
