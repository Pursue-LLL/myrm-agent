# execution_cache 模块

---

## 架构概述

Chat 级 `BuiltExecutionUnit` 池（SkillAgent + BrowserSession）。WebUI/Channel/Wakeup 走 POOLED；Cron/Eval/Kanban 走 EPHEMERAL。镜像 `ChatRuntimePoolRegistry` 生命周期语义。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出 | ✅ |
| `registry.py` | 核心 | acquire（`holds_turn_guard` 标明调用方即持锁回合，见“指纹变化的生效路径”）/release/refresh_unit/guard_turn/idle_evict（支持动态空闲回收超时配置、原子移出与 gc.collect）；`snapshot_warm_units` / `is_scope_turn_active` 供 catalog 热更新；进程级 singleton | ✅ |
| `types.py` | 核心 | `ExecutionMode`、`BuiltExecutionUnit.teardown()` | ✅ |
| `fingerprint.py` | 核心 | `compute_execution_fingerprint`（模型类字段统一经 `_model_sig` 提取 build 固化签名，含主/兜底/推理/轻量/视觉/视频模型，且将 temperature/model_kwargs（LLM 实例 build 期固化）与 credential_pool_strategy（CredentialPool build 期固化）纳入签名；结构化配置经 `_credential_free_json` 剔除 api_key/api_keys/apiKeys/_oauthToken/localApiKey/bearer_token 等凭据后进哈希（媒体生成/搜索服务/嵌入/重排/provider 池/OpenAPI 服务/隐私路由）；技能/MCP/harness epoch/`engine_params` 含 MoA preset 激活态/安全配置/记忆配置（含确认开关/隔离策略/会话搜索/高级检索）/执行网络/通知/看板（含默认看板）/子代理/委托/网页抓取/域名恢复——覆盖所有 build 期固化的用户可配置输入；活跃 Goal 经关键字参数 `has_active_goal`（存储真值）进指纹；排除凭据、传输头、每 run 状态与全局静态配置；YOLO 启用时间戳 `yolo_mode_enabled_at` 不进指纹） | ✅ |
| `unit_ops.py` | 核心 | capture/apply/detach wrapper ↔ unit | ✅ |
| `session_lifecycle.py` | 核心 | `resolve_execution_mode`、`finalize_agent_session`（release 前 refresh_unit） | ✅ |
| `prewarm/` | 核心 | Turn1 冷启动预热（见 [prewarm/_ARCH.md](prewarm/_ARCH.md)） | ✅ |

测试：`tests/services/agent/execution_cache/`（registry + fingerprint 全 build 配置 bust 覆盖 + prewarm coordinator）· `tests/api/agent/test_prewarm_api.py` · Chrome E2E `tests/e2e/test_execution_cache_chrome_e2e.py`（prewarm log + 2msg1build）。

---

## 模式

| 入口 | execution_mode | 行为 |
|------|----------------|------|
| WebUI / Channel / Wakeup | POOLED | 同 chat 复用 BuiltExecutionUnit |
| Cron / Eval / Kanban | EPHEMERAL | 每条消息 build + close |

删 chat：`chat_disposal` 调用 `close_execution_cache_for_chat_all_agents`。

---

## 指纹变化的生效路径

`acquire` 遇到指纹变化时替换旧单元：先 `teardown()` 旧单元（关闭其浏览器/桌面会话与 SkillAgent），再重建。

- **其他回合正在运行**：该 scope 的 turn lock 被另一个回合持有时，只推迟替换并复用旧单元（保护运行中的回合），回合结束后的下一次 `acquire` 再替换。
- **持锁回合自己 acquire**：`guard_turn` 保证同 scope 的回合串行，持锁者就是唯一使用该单元的回合，经 `holds_turn_guard=True` 声明身份后立即替换。`stream_pipeline` 整个回合都在 `guard_turn` 内，经 `coalesced_acquire(..., holds_turn_guard=True)` acquire，所以所有 POOLED 入口（编排器、无人值守目标触发、自动续跑、语音、OpenAI 兼容、fast 模式）在指纹变化后的第一个回合就跑在新单元上，不依赖回合前的预热。
- **合并到预热的在途 acquire**：`coalesced_acquire` 会把持锁回合合并到预热（不持锁）已在途的 acquire 上，该 acquire 可能已被推迟。持锁方在合并结束后复核 `is_warm`，不匹配就以持锁身份自己完成替换。
- **预热的作用**：`join_for_turn` / `ensure_warming` 只把构建挪到回合之前以缩短首 token 延迟，不决定单元是否被替换。

同一 chat 在交互与无人值守之间每翻转一次（指纹含 `unattended_mode`、`channel_name`），就重建一次单元。同一目标的连续无人值守回合共享一个单元：目标触发器每次触发都会重写 YOLO 启用时间戳，它不进指纹（不论有无 YOLO 超时），所以回合之间不重建，单元持有的浏览器会话也不被关闭。

---

## 指纹覆盖审计清单

`compute_execution_fingerprint` 必须覆盖**所有 build 期固化（solidified into `build_general_agent` 输出）的用户可配置字段**。新增/调整 build 输出时，按此清单双向核对：

### AgentRuntimeSpec 输出面
| 输出 | 输入字段（均在指纹中） |
|------|------------------------|
| LLM 实例（主/兜底/推理/轻量/视觉/视频） | model/base_url/max_context_tokens/supports_vision/supports_video/custom_model_def + temperature + model_kwargs（凭据/传输头剔除后，见排除项）+ credential_pool_strategy（固化进 CredentialPool） |
| system_prompt | prompt_mode / engine_params / search_depth（经 max_iterations/engine_params 间接覆盖）/ unattended_mode / enable_answer_tool |
| tool_groups | 全部 `enable_*` flag + file_access_mode + image/video/tts params 存在性 |
| skill_ids / skill_configs | skill_ids / skill_configs / skill_config_version |
| mcp_servers / openapi_services | mcp_config / openapi_services |
| memory_namespaces | enable_memory / incognito / memory_policy / channel_name |
| workspace_binding | declared_allowed_roots |
| 其余（max_iterations/locale/engine_params 等） | 同名字段 |

### 工具挂载点（_setup_* / factory 直挂）
| 工具 | build 固化字段 |
|------|---------------|
| web_search | search_service_cfg（search_service/api_base/extra_params/provider_chain；api_key 排除） |
| web_fetch | enable_advanced_retrieval / reranker_config / embedding_config / fetch_raw_webpage |
| browser | auto_restore_domains / browser_source / dialog_policy |
| 媒体生成（image/video/tts） | image/video/tts params（model/fallback/size/quality/voice；api_key 排除） |
| skill_market / skill_manage | enable_skill_market / skill_manage_mounted（`enable_skill_manage` 或 `/learn` 的 `force_skill_manage` 折叠；与 factory 挂载判定同源） |
| memory 写入 | memory_require_confirmation / enable_memory_auto_extraction / memory_extraction_preset |
| memory 召回 | embedding_config（稠密召回）/ reranker_config + enable_advanced_retrieval（重排；开关为关时不挂重排） |
| kanban | kanban_tool_mode / kanban_default_board_id |
| goal（complete_goal_tool + 强制 planning） | has_active_goal：wrapper 之外的会话状态，由调用方读存储真值（`GoalRegistry.has_active_goal`）传入；builder 按已注册的 provider 挂载，交互回合在编排器内先注册 provider 再构建 |
| external_agents | external_agents（name/command/args/authMode 固化；api_key 剔除） |
| openapi_services | openapi_services（spec/base_url/endpoints 固化；整个 auth 子树剥离） |

### 排除项（有意不进指纹）
- 凭据：api_key/api_keys/apiKeys/_oauthToken/_oauthBaseUrl/localApiKey/bearer_token/password/client_secret（`_model_sig` / `_credential_free_json`）
- 传输头：model_kwargs 内 `extra_headers` 整棵子树（`_TRANSPORT_HEADER_KEYS`）：resolve 期注入的 X-Sandbox-Id/X-Telemetry-Token/Authorization 仅运行时鉴权，轮换不 bust
- OpenAPI 服务 `auth` 整棵子树（`_openapi_services_sig`）：auth 仅运行时鉴权、不塑形 build 输出（工具名/描述来自 spec + selected_endpoints），含 auth.type 变化均不 bust
- 每 run 状态：kanban_current_task_id、quote、timezone、reasoning_display_mode（`force_skill_manage` 不在此列：它决定工具是否被 build，已折叠进 `skill_manage_mounted`）
- YOLO 启用时间戳：`security_config_raw` / `agent_security_raw` 内的 `yolo_mode_enabled_at`，无条件排除（`_YOLO_STAMP_KEYS`）。时间戳只在运行时为 YOLO 超时计时（`batch_processor/core.py`），读取的是 stream_pipeline 每 turn 重应用的安全配置，build 期没有读取方；目标触发器、看板 runner 在构建时给配置副本补写它，IM `/yolo on <超时>` 经请求的 `SecurityOverlaySpec.yolo` 在每次重载后写入它，进指纹会让每次重写都拆掉单元。复用的单元每 turn 按最新时间戳判定 YOLO 是否过期；`yolo_mode_timeout` 本身仍进指纹（超时改了就重建）
- 每 turn 刷新：privacy_enabled 等 10 个隐私字段 + enable_plan_confirm（stream_pipeline 每 turn 重应用）
- 全局静态：event_log_backend、tail_budget_ratio
- 前端已发送但 converter 未接入（死字段）：pre_compact_enabled / pre_compact_budget_tokens
