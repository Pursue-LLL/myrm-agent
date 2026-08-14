# execution_cache 模块

---

## 架构概述

Chat 级 `BuiltExecutionUnit` 池（SkillAgent + BrowserSession）。WebUI/Channel/Wakeup 走 POOLED；Cron/Eval/Kanban 走 EPHEMERAL。镜像 `ChatRuntimePoolRegistry` 生命周期语义。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出 | ✅ |
| `registry.py` | 核心 | acquire/release/refresh_unit/guard_turn/idle_evict；`snapshot_warm_units` / `is_scope_turn_active` 供 catalog 热更新；进程级 singleton | ✅ |
| `types.py` | 核心 | `ExecutionMode`、`BuiltExecutionUnit.teardown()` | ✅ |
| `fingerprint.py` | 核心 | `compute_execution_fingerprint`（模型类字段统一经 `_model_sig` 提取 build 固化签名，含主/兜底/推理/轻量/视觉/视频模型与隐私路由；结构化配置经 `_credential_free_json` 剔除 api_key/api_keys/apiKeys/_oauthToken 后进哈希（媒体生成/搜索服务/嵌入/重排/provider 池）；技能/MCP/harness epoch/`engine_params` 含 MoA preset 激活态/安全配置/记忆配置（含确认开关/隔离策略/会话搜索/高级检索）/执行网络/通知/看板（含默认看板）/子代理/委托/网页抓取/域名恢复——覆盖所有 build 期固化的用户可配置输入；排除 api_key 等凭据池字段、每 run 状态与全局静态配置） | ✅ |
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

删 chat：`chat_crud` 调用 `close_execution_cache_for_chat_all_agents`。

---

## 指纹覆盖审计清单

`compute_execution_fingerprint` 必须覆盖**所有 build 期固化（solidified into `build_general_agent` 输出）的用户可配置字段**。新增/调整 build 输出时，按此清单双向核对：

### AgentRuntimeSpec 输出面
| 输出 | 输入字段（均在指纹中） |
|------|------------------------|
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
| skill_market / skill_manage | enable_skill_market / enable_skill_manage |
| memory 写入 | memory_require_confirmation / enable_memory_auto_extraction / memory_extraction_preset |
| kanban | kanban_tool_mode / kanban_default_board_id |

### 排除项（有意不进指纹）
- 凭据：api_key/api_keys/apiKeys/_oauthToken/_oauthBaseUrl/credential_pool_strategy（`_model_sig` / `_credential_free_json`）
- 每 run 状态：kanban_current_task_id、quote、force_skill_manage、timezone、reasoning_display_mode
- 每 turn 刷新：privacy_enabled 等 10 个隐私字段 + enable_plan_confirm（stream_pipeline 每 turn 重应用）
- 环境级固定：client_surface；全局静态：event_log_backend、tail_budget_ratio
- 前端已发送但 converter 未接入（死字段）：pre_compact_enabled / pre_compact_budget_tokens
