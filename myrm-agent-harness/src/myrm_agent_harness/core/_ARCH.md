# core/

## Overview
Framework-agnostic foundation layer. Provides security, config, events, hooks, artifacts, and feature flags capabilities shared by both `agent/` and `toolkits/`, eliminating coupling between them.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Core layer entry — module docstring only, no re-exports at this level. | — |
| context_vars.py | Core | Cross-layer ContextVar registry shared by agent/ and toolkits/ without coupling. Holds `protected_paths_var` (Goal-scoped protected path patterns) so the sandbox executor enforces the same Goal protection as the file tools and the shell pre-flight, `session_access_roots_var` (the directories the server granted before a run starts; it seeds the run's container) and `access_grants_var` (the run's `AccessGrants`: `declared`, `session` and `once` roots, opened once at run entry by `open_access_grants` (which turns the declared roots into real paths, as session and one-call roots already are when granted, so a link put in a root's place later does not move it) and only mutated in place afterwards, because a graph node runs in a copied context and a rebound ContextVar would never reach the next node; `standing_access_roots` / `reachable_access_roots` are what the executor and the sandbox read, so they reach the same directories the permission engine judged by; `agent/security/session_access.py` owns the grants), `approval_session_var` (approval-routing session key) so the sandbox executor resolves the active approval session without importing agent/, and the approval-note hand-off — `current_tool_call_id_var` (the call a running tool body belongs to) plus `approval_notes_var` with `publish_approval_notes` / `stash_approval_note` / `claim_approval_note` — so a gate a human answered can hand its note to the tool-call middleware without toolkits/ importing agent/; the note store is a mutable dict because a tool body runs in a copied context, where rebinding a ContextVar is invisible to the middleware while mutating the published dict is not. `agent/middlewares/_session_context` is the accessor for agent code. `source_indexer_var` (type `SourceIndexer`) carries the run's source numbering — `StreamExecutor.execute` binds the run tracker's `index_for` — so a tool numbers the sources of its result with the index of the card the stream issues for them; unbound outside a run, a tool numbers from 1. `scoped_value` binds a ContextVar for a `with` block and restores it on exit. | ✅ |
| skill.py | Core | 技能声明领域常量 — `DEFAULT_ALLOWED_TOOLS`（编译技能默认 allowed-tools SSOT）。供 `backends/skills/workflow_compiler` 与 `toolkits/*` 共享，避免 toolkits→backends 依赖。 | ✅ |
| paths.py | Core | 持久化卷根原语 — `PERSISTENT_ROOT_ENV` / `DEFAULT_PERSISTENT_ROOT` / `get_persistent_root` / `get_workspace_root` / `get_context_root` / `get_memories_root`。每次调用时读取 `MYRM_PERSISTENT_ROOT`，部署层在导入之后设置也生效。放在 core 而非 runtime：`toolkits/` 需要根路径但禁止 import `runtime/`，`runtime.paths.execution_paths` 转发这些名字。 | ✅ |
| message_origin.py | Core | 消息来源原语 — `is_user_authored_human_message`（用户亲写的 HumanMessage，区别于运行时代用户追加并标记 `is_system_synthetic` 的消息）、`runtime_human_message`（构造这类被标记消息的唯一入口）、`runtime_system_message` 与 `is_runtime_system_block`（运行时只写给执行模型的系统块——数据边界规则、金丝雀指令、会话目录——的构造与识别，顾问模型的历史据此排除它们）、`last_user_authored_index`（当前回合的起点，没有则为 -1）、`count_user_authored_messages`（回合数）。审批、安全、记忆上下文与上下文管理读同一条回合边界；放在 core 使 `toolkits/` 的尾部注入器无需 import `agent/`。`runtime_human_message` 与 `last_user_authored_index` 同时从 `myrm_agent_harness.api` 公开：宿主自己的中间件写运行时通知、读回合起点时只走这一入口，通知才不会被当成用户的新一轮发言。 | ✅ |
| message_tail.py | Core | `append_block_to_last_user_message` — 每回合变化的内容只放在用户自己的最新消息尾部，不放在其后的运行时通知上。系统提示与更早历史因此逐字节不变，保住提示缓存前缀；同一次运行的两个请求之间增删通知，也不会带动该块位移。 | ✅ |
| thinking_blocks.py | Core | 签名推理块（Anthropic 系 `thinking` / `redacted_thinking`）的共享定义 — 两种块的 TypedDict、`coerce_thinking_blocks`（校验并复制）、`ThinkingBlockAssembler`（按服务商 content index 从流式增量拼出完整块）、`thinking_blocks_text`（token 估算用的推理文本）、`carries_signed_blocks`（一次请求是否会回放至少一个块；改写更早的消息之前先问它）、以及 `without_thinking_blocks`（提示词不属于该会话的调用要去掉块）。传输层、聊天模型适配器、上下文管线、回放守卫与估算器共用同一种块形状。 | ✅ |

| Submodule | Description |
|-----------|-------------|
| security/ | Security primitives — PII detection, content boundary, prompt injection guard, SSRF guard, audit, path security, execution policy, credential vault (label→password/TOTP for tool injection). |
| config/ | Framework-agnostic configuration types — LLMConfig, CustomModelDef. |
| events/ | Event type definitions — AgentEventType, AgentStreamEvent, THINKING_TAG_NAMES. |
| hooks/ | Hook lifecycle definitions — HookEvent, HookDefinition variants, HookResult, event payloads. |
| artifacts/ | Artifact type constants — ArtifactType enum, extension/MIME mappings, inference utilities. |
| features/ | Feature Flags — registration, lifecycle management, runtime querying. |

## Key Dependencies

- No internal dependencies (foundation layer — depended upon by agent/ and toolkits/)
