# api/integrations/

## 架构概述

集成目录、MCP 检查、OAuth 凭证与本机 Ollama 探测 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | External integrations API module | ✅ |
| `catalog.py` | 模块 | Integration Catalog API endpoints；透传 registry 归一化后的显式 `deployment_scope`（`local_tauri_only` / `all_modes`），透传 `post_connect_guide`。 | ✅ |
| `integration_memory.py` | 模块 | REST API layer for Integration Memory. | ✅ |
| `credential_pool.py` | 模块 | 密钥池运行时观测与外部凭证（1Password / Bitwarden）安全验证端点 | ✅ |
| `llms.py` | 模块 | LLM 验证 / 可达性检查 / OpenAI-compatible `discover-models`（SSRF 保护 + 环境自适应白名单，本地/桌面模式放行 loopback、RFC1918 私网、Tailscale CGNAT 与 .local mDNS 分机免密探测，显式阻断 169.254.0.0/16 Link-Local；SaaS 模式严格物理隔离）/ 模型能力探测（`model-info`/`model-info/batch`）/ `speed-test`（`verify`、`check-reachability`、`speed-test` 先经 `resolve_oauth_marker` 把 WebUI 的订阅占位 key 换成已存的新鲜令牌，订阅不可用或目标主机不是签发主机时按错误返回）/ `check-reachability` 用 harness `probe_llm_health` 做单次最小提示探测（15s 截止，覆盖真实厂商首 token 延迟），失败按 `timeout` / `provider_error` 分类并原样透传上游原因（如 `Invalid credential`），不再统一报「无响应」/ 三个探针（`verify`、`check-reachability`、`speed-test`）每次都真实问上游：进程里没有 LiteLLM 响应缓存（`toolkits/llms/config.py` 不安装；它按模型 + 消息命中，与 Key / 端点无关，留着就会让换了 Key 或端点的探针被上一次的成功答成成功），`check-reachability` 自带的 30 秒结果缓存按整个请求（模型、端点、Key、代理、模型参数）的 blake2b 摘要分键，Key 不以明文留在进程级字典里 / 模型切换压缩预检 `model-switch-preflight`（复用 harness `ContextConfig` 压缩阈值公式 + `infer_model_tier` tier 推断，`prompt_mode` 非 full 时回退默认比例；传入 `turn_count` 时复用 `ContextBudget.calculate_dynamic_thresholds` 按会话紧张度收紧阈值，与运行时压缩口径一致。传入 `chat_id` 时消费压缩无效 streak（anti-thrash）：streak≥2 且 tokens<目标窗口 90% 判定不压缩、≥90% 仍判定压缩（对齐 `should_block_automatic_compression`）。eco_mode（阈值 ×0.80，运行时压缩更早）为漏报方向、hot-cache（5 分钟活跃跳过压缩）为略早方向，均为瞬态状态不模拟；预检基于上一轮快照不含未发送消息增量，判定与文案按「可能触发」措辞 | ✅ |
| `mcp/` | 子包 | MCP verify / scan / options / resource 端点，以及并入同一路由的 Registry 搜索 / 详情代理与本地连通性探测 `/probe`；详见 [mcp/_ARCH.md](mcp/_ARCH.md) | ✅ |
| `models_dev.py` | 模块 | models.dev 模型目录代理（`GET /models-dev`）：出站请求走受企业网络兼容设置管辖的 httpx 客户端；约 6 MB 的目录以字节缓存 5 分钟、不解析直接拼进成功信封，并发请求共享同一次下载（上游不通时也只试一次），上游失败一律 502 且不缓存 | ✅ |
| `oauth/` | 子包 | OAuth 连接的 HTTP 层：个人凭证存取、MCP 与 Google Workspace 授权码 + PKCE、xAI 设备码登录、模型供应商订阅登录的状态与断开、授权结束后的结果页；详见 [oauth/_ARCH.md](oauth/_ARCH.md) | ✅ |
| `ollama.py` | 模块 | 本机 Ollama 探测与一键连接端点：`GET /ollama/chat-model` 读取 `/api/tags`，用 `/api/show` 的 capabilities 排除 embedding 模型、无工具调用能力的模型与云端转发模型，为首个能对话且支持工具调用的已装模型给出连接地址；只读用户已安装的模型，不安装、不下载 | ✅ |
| `retrieval.py` | 模块 | 检索服务配置验证：`POST /embedding` 嵌入一段短文本、`POST /reranker` 对两条短文档重排，都经产品运行时同一套工厂（`get_embedding_service` / `get_reranker_service`）真实调用上游；每次探测的文本都不同，按文本命中的缓存（嵌入服务自带的、网关上的）因此答不了探测；失败仍返回 HTTP 200 + `success=false`，`message` 写明原因（Key 被拒 / 模型或端点未知 / 限流 / 额度耗尽 / 端点不可达 / TLS 证书被拒），`error` 是抹去 Key 的异常文本；设置页的 Next 代理 `app/api/retrieval/validate/*` 指向此处 | ✅ |
| `router.py` | 路由 | Integrations API router | ✅ |
| `search.py` | 模块 | Search provider manifest (`GET /providers`) 与 live probe 验证 (`POST /verify`)；manifest 驱动 Settings 下拉 | ✅ |
| `web_fetch.py` | 模块 | Web fetch escalation verify API；`POST /verify` 校验 Jina/Firecrawl 凭据（含 `inherit_from_search` 继承 / 自托管 `api_base`） | ✅ |
