# api/integrations 模块架构


---

## 架构概述

外部服务集成接口。提供 LLM、搜索、MCP、检索服务的验证端点，以及 **Integration Catalog**（预配置服务目录）供用户一键连接第三方服务。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `router.py` | ✅ 入口 | 子路由注册 |
| `llms.py` | ✅ 核心 | LLM 提供商验证（连接测试、模型列表、轻量可达性探测 `/check-reachability` 含 30s TTL 缓存、批量流式测速 `/speed-test` 测 TTFT+TPS） |
| `mcp.py` | ✅ 核心 | MCP 服务器验证（SSRF 防护、响应验证） |
| `retrieval.py` | ✅ 核心 | 检索服务验证（Embedding、Reranker） |
| `search.py` | ✅ 辅助 | 搜索服务验证 |
| `catalog.py` | ✅ 核心 | Integration Catalog API（预配置服务目录浏览/搜索） |
| `integration_memory.py` | ✅ 核心 | Integration Memory API（同步/浏览/状态/删除集成记忆数据树，支持按 provider 批量清除） |
| `oauth.py` | ✅ 核心 | OAuth 凭证管理（AES-256-GCM 加密存储、CRUD、断开时可选清除同步数据） |
| `mcp_oauth.py` | ✅ 核心 | MCP OAuth 2.0 + PKCE 授权流 API（/start 生成授权 URL、/callback 换取 token、/status 查询状态、DELETE 断开授权） |
| `im_contacts.py` | ✅ 辅助 | IM 联系人同步（飞书/钉钉等通讯录数据） |

---

## Integration Catalog

预配置服务目录系统，允许用户从前端"服务目录"页面一键连接热门第三方服务（Notion、GitHub、Slack、飞书、钉钉等）。

**架构分层**：
- **数据层**：`app/core/integrations/catalog/` — 包含数据模型（`models.py`）、注册表（`registry.py`）、预配置 JSON 数据（`data/*.json`）
- **API 层**：`app/api/integrations/catalog.py` — 提供 `GET /catalog`（列表/搜索/分类过滤）和 `GET /catalog/{id}` 端点
- **前端**：Settings → 通信与集成 → 服务目录

**工作原理**：
1. CatalogRegistry 单例从 `data/*.json` 文件懒加载预配置的 `CatalogEntry`
2. 每个 CatalogEntry 包含 MCP/OpenAPI 连接模板 + 认证要求
3. 前端展示服务卡片墙，用户点击"连接"后弹出引导对话框
4. 连接操作实质是将预配置模板写入用户的 MCP 配置（复用现有 MCP 管理体系）

**多凭证支持**：
- `AuthRequirements.credential_fields`（`CredentialField` 列表）支持需要多个凭证的服务（如飞书 App ID + App Secret）
- 每个 `CredentialField` 通过 `inject` 字段声明注入方式：`arg_placeholder`（替换 args 中的占位符 `{{key}}`）或 `env`（写入 env 变量）
- `MCPPreConfig.env` 支持预设非密钥环境变量（如钉钉的 `ACTIVE_PROFILES`）
- 前端连接对话框根据 `credentialFields` 动态渲染多输入框，无 `credentialFields` 时回退到旧单密钥模式

---

## 依赖关系

- `app/core/security/mcp/`：MCP 安全验证（SSRF、响应大小）
- `app/core/integrations/catalog/`：Integration Catalog 数据模型与注册表
