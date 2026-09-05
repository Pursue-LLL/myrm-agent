# api/integrations/

## 架构概述

集成目录、OAuth 凭证与 Hardware Cookbook HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External integrations API module | ✅ |
| `catalog.py` | 模块 | Integration Catalog API endpoints；透传 registry 归一化后的显式 `deployment_scope`（`local_tauri_only` / `all_modes`），透传 `post_connect_guide`。 | ✅ |
| `hardware.py` | 模块 | 硬件推荐 API：检测本地硬件、计算 64K KV Cache 显存开销 (FP16/Q8/Q4)、划分 5 档 Reference Ladder 硬件段位、估算 Tokens/s 并生成 Ollama 模型适配度推荐，含 Ollama pull 自动派生 64K agentic Modelfile 与 delete 联动清理端点。 | ✅ |
| `hardware_calculator.py` | 模块 | 硬件指标与 64K KV Cache 显存测算纯函数工具模块。 | ✅ |
| `im_contacts.py` | 模块 | Lightweight search users API for IM group management. | ✅ |
| `integration_memory.py` | 模块 | REST API layer for Integration Memory. | ✅ |
| `credential_pool.py` | 模块 | 密钥池运行时观测与外部凭证（1Password / Bitwarden）安全验证端点 | ✅ |
| `llms.py` | 模块 | LLM 验证 / 可达性检查 / OpenAI-compatible `discover-models`（SSRF 保护 + 环境自适应白名单，本地/桌面模式放行 loopback、RFC1918 私网、Tailscale CGNAT 与 .local mDNS 分机免密探测，显式阻断 169.254.0.0/16 Link-Local；SaaS 模式严格物理隔离）/ 模型能力探测（`model-info`/`model-info/batch`）/ `speed-test` / 模型切换压缩预检 `model-switch-preflight`（复用 harness `ContextConfig` 压缩阈值公式 + `infer_model_tier` tier 推断，`prompt_mode` 非 full 时回退默认比例；传入 `turn_count` 时复用 `ContextBudget.calculate_dynamic_thresholds` 按会话紧张度收紧阈值，与运行时压缩口径一致。传入 `chat_id` 时消费压缩无效 streak（anti-thrash）：streak≥2 且 tokens<目标窗口 90% 判定不压缩、≥90% 仍判定压缩（对齐 `should_block_automatic_compression`）。eco_mode（阈值 ×0.80，运行时压缩更早）为漏报方向、hot-cache（5 分钟活跃跳过压缩）为略早方向，均为瞬态状态不模拟；预检基于上一轮快照不含未发送消息增量，判定与文案按「可能触发」措辞 | ✅ |
| `mcp.py` | 模块 | MCP verify/scan/probe API；`/probe` 返回 `reason_code/recommended_mode/should_block_connect` 结构化语义（含 `tls_verification_failed`、`connection_unreachable`、`probe_failed_unknown`）；unexpected fallback 返回脱敏文案、默认推荐 `verify_local_network_and_editor`，并在服务端以去凭据/去 query 的 target 日志保留异常，支持 cloud loopback guard UX。 | ✅ |
| `google_workspace_oauth.py` | 模块 | Google Workspace OAuth 2.0 + PKCE；readonly/write tier；写入 oauthCredentials（不含 client_secret） | ✅ |
| `google_workspace_oauth_flow.py` | 模块 | OAuth PKCE 会话态、scope tier、redirect 解析与 Google userinfo 辅助 | ✅ |
| `mcp_oauth.py` | 模块 | MCP OAuth 2.0 + PKCE authorization flow API. | ✅ |
| `model_specs.py` | 模块 | Settings Hardware Cookbook 使用的 Ollama 模型规格数据源。 | ✅ |
| `oauth.py` | 模块 | OAuth 凭证管理 API。提供个人 SaaS 集成凭证的加密存储、查询和撤销，支持断开时可选清除同步数据。 | ✅ |
| `xai_oauth.py` | 模块 | xAI OAuth device-code flow；SuperGrok 订阅授权；复用 oauth_store 持久化 | ✅ |
| `provider_oauth.py` | 模块 | Provider OAuth flows (Anthropic PKCE + OpenAI/Copilot device-code)；模型提供商订阅登录；OAuth token 注入 model_resolver 链路 | ✅ |
| `retrieval.py` | 模块 | Retrieval Service Configuration Validation API | ✅ |
| `router.py` | 路由 | Integrations API router | ✅ |
| `search.py` | 模块 | Search provider manifest (`GET /providers`) 与 live probe 验证 (`POST /verify`)；manifest 驱动 Settings 下拉 | ✅ |
| `web_fetch.py` | 模块 | Web fetch escalation verify API；`POST /verify` 校验 Jina/Firecrawl 凭据（含 `inherit_from_search` 继承 / 自托管 `api_base`） | ✅ |
