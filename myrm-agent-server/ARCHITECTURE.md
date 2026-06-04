# MyrmAgent 服务端架构

> **许可**: MIT。单机业务编排与 API 层（本仓库）。

> 🔄 **AI 自维护规则**（必读）：任何功能、架构、写法更新后，必须更新相关目录的子文档。

---

## 分形文档系统规范

本项目采用**分形自指文档系统**，实现局部与整体的双向绑定。

### 规则一：文件夹架构文档

每个文件夹必须包含 `_ARCH.md`（不使用 README.md），格式如下：

```markdown
# {文件夹路径} 模块架构

{三行以内的极简架构说明}

## 文件清单

| 文件   | 地位     | 职责   | I/O/P |
| ------ | -------- | ------ | ----- |
| xxx.py | 核心入口 | 做什么 | ✅    |
```

### 规则二：文件头注释

每个 Python 文件开头必须包含三行极简注释：

```python
"""
@input: 依赖 {其他文件的 Pos 描述}
@output: 对外提供 {什么能力}
@pos: {在系统中的地位}

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""
```

### 规则三：语义链接网络

在 `@input` 中直接引用其他文件的 `@pos` 描述，形成横向连接。

**示例**：

```python
"""
@input: 依赖 sandbox_executor.py 的「沙箱执行引擎」，依赖 llm.py 的「LLM 调用层」
@output: 对外提供代码执行工具
@pos: 代码执行元工具
"""
```

---

## 系统全景

```
┌──────────────────────────────────────────────────────────────────┐
│                         MyrmAgent                               │
├──────────────────────────────────────────────────────────────────┤
│  app/                                                            │
│  ├── api/           HTTP 接口层 - FastAPI 路由与请求处理         │
│  ├── schemas/       共享 Pydantic DTO（api + services 共用）   │
│  ├── services/      业务服务层 - 按域组织(agent/chat/wiki/...)   │
│  ├── ai_agents/     AI Agent 定义层 - Agent 配置、Prompt、工作流 │
│  ├── channels/      渠道消息层 - 多平台IM渠道框架(14+提供商)     │
│  ├── core/          核心基础设施 - 安全/Cron/检索/监控/工具/infra│
│  ├── adapters/      适配器层 - 框架 Protocol 的业务实现          │
│  ├── database/      数据层 - ORM/DTO/连接池 + Repository 仓储隔离层 │
│  ├── middleware/     中间件层 - 认证/安全/限流/文本清洗           │
│  ├── platform_utils/ 平台抽象层 - 本地/沙箱模式差异化实现       │
│  ├── tasks/         后台任务 - 异步任务执行器与调度              │
│  └── config/        配置层 - 环境变量、设置、部署模式            │
├──────────────────────────────────────────────────────────────────┤
│  支撑模块                                                        │
│  ├── scripts/         运维脚本（部署、CLI）                      │
│  └── tests/           测试套件                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 一级目录说明

| 目录                  | Pos（地位）  | 职责                                                                                                                             |
| --------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `app/api/`            | HTTP 入口层  | FastAPI 路由、请求/响应处理、WebSocket                                                                                           |
| `app/services/`       | 业务服务层   | 按业务域组织（agent/chat/wiki/config/skills/memory/...）                                                                         |
| `app/ai_agents/`      | Agent 定义层 | AI Agent 配置、Prompt 模板、子 Agent 定义                                                                                        |
| `app/channels/`       | 渠道消息层   | 多平台 IM 渠道框架：14+ 提供商（Feishu/Slack/Discord/Telegram/WhatsApp 等）、消息总线、路由、i18n、安全、可靠性。详见 [CHANNELS_SYSTEM.md](app/channels/CHANNELS_SYSTEM.md) |
| `app/core/`           | 核心基础设施 | 安全认证、Cron 引擎、检索器、监控、通用工具                                                                                      |
| `app/adapters/`       | 适配器层     | 实现 Harness 框架层定义的 Protocol（数据源、存储等）                                                                             |
| `app/database/`       | 数据层       | SQLAlchemy ORM/DTO、连接管理及 Repositories 仓储模式                                                                             |
| `app/middleware/`     | 中间件层     | 认证告警、Webhook 安全、文本清洗、沙箱认证                                                                                       |
| `app/platform_utils/` | 平台抽象层   | 本地/沙箱模式差异化实现（文件存储、会话工厂、checkpointer 注入）                                                                 |
| `app/tasks/`          | 后台任务层   | 异步任务执行器、后台 worker                                                                                                      |
| `app/config/`         | 配置层       | 环境变量、设置、部署模式检测、预检                                                                                               |
| `tests/`              | 测试套件     | 单元测试、集成测试、API 测试                                                                                                     |
| `scripts/`            | 运维脚本     | 部署脚本、CLI、分形文档门禁 `check_fractal_docs.py`（默认校验 `app/**` 目录均含 `_ARCH.md`；`--strict-headers` 为增量 adopting） |
| `docker/`             | 容器构建     | Server runtime：`Dockerfile.official`（源码双 wheel）；`../Dockerfile`（PyPI / 预构建 wheel）；`sandbox/` 技能沙箱镜像 |
| `deployments/`        | 部署配置     | Prometheus 规则等运维配置                                                                                                        |
| `searxng/`            | 搜索引擎配置 | SearXNG 搜索引擎部署配置                                                                                                         |

---

## 核心架构约束

### 0. 分层定位优先于功能堆叠

`myrm-agent-server` 是**单机业务编排层**：

- 在 `local` / `tauri` 场景中，它直接作为单机单用户后端运行。
- 在 `sandbox` 场景中，它仍然是**单个用户沙箱内部**的业务后端，而不是 SaaS 多租户控制面。
- 它负责承接自定义智能体、聊天、知识库、Cron、渠道、审批体验等产品能力，但不负责多租户身份、沙箱池化、全局路由、配额聚合等控制平面职责。
- 全面剥离多租户感知：API 路由、Query 及内部调用已彻底移除 `user_id` 依赖，作为纯粹的单租户应用在独立的 `MYRM_DATA_DIR` 中运行。

因此，本层新增任何竞品借鉴项前，都必须先确认：该能力究竟属于业务编排，还是应该下沉到 `myrm-agent-harness`、或上收至外部控制服务（SaaS 部署场景）。

### 代码智能（外部 MCP 集成）

- 代码智能通过外部 MCP 服务提供。用户可在 **Settings → Communication & Integrations** 的 Integration Catalog 中一键接入 `code-review-graph`（28 工具）或 `CodeGraph`（10 工具）等社区 MCP 服务。

### 0.05 Agent 模型凭据（WebUI only）

- **HTTP 装配**：`app/services/agent/params/` 解析 `ModelSelection` 与用户 Provider 行；缺失密钥时抛出 `ConfigIncompleteError`（**禁止** `BASIC_*`/`LITE_*` 进程 env 回退）。
- **平台默认模型**：后台 judge/embedding 等读 WebUI via `platform_config.py`；`model_resolver._fallback_model_from_providers` 仅从 `defaultModelConfig` + `providers` 解析，无 env 回退。
- **启动提示**：`pre_flight.py` 在 local/tauri 下对未配置 WebUI 默认模型输出 **warning**（不阻塞启动）。
- **前端 gate**：`messageRequest.validateChatModelConfig` 发送前拦截无 provider / 无 defaultModel；`LocalCapabilitiesBanner` / `SearchSetupChip` / Settings `SearchSection` 一键激活本地模型与免费搜索（SearXNG `:8081` / DuckDuckGo）；`GET /config/onboarding/probe-local` 统一探测；deploy `docker compose --profile search` 自动启动 SearXNG。

### 0.06 环境变量分层（[P]/[O]/[X]/[T]/[S]）

| 层 | 来源 | 运行时 | 示例 |
|----|------|--------|------|
| **[P]/[O]** | `.env` → `AppSettings` | server 进程 | `DEBUG`, `MCP_*`, DB 路径派生 |
| **[X] 业务** | WebUI Settings → DB → inject | 请求路径注入 harness | LLM provider、search、embedding、reranker |
| **[T] 测试** | `.env.test` → `tests/support/test_secrets.py` | **仅 pytest** | `BASIC_*`, `LITE_*`, E2E toggles |
| **[S] 沙箱** | Control Plane 容器注入 / `.env.sandbox` | sandbox 进程 env | `CONTROL_PLANE_*`, `MYRM_MASTER_KEY`, `MYRM_PUBLIC_WIKI_VOLUMES` |

- **环境变量清单**：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）为唯一权威索引；业务配置不得写入 `.env`。
- **[S] 注入契约**：沙箱创建时由控制服务注入环境变量；`tests/unit/test_sandbox_env.py` 与 `validate_for_sandbox()` 双向对齐。
- **部署能力注册表**：`app/platform_utils/deployment_capabilities.py` — 启动时构建语义能力位，替代散落的 `is_sandbox()` 分支。
- **单租户认证**：`app/middleware/auth.py` — local 回环 / sandbox CP HMAC 验签（`cp_proxy.py`）→ `SANDBOX_API_KEY` → 回环 / WebUI Remote `SANDBOX_API_KEY`。
- **WebUI 浏览器登录**（仅 local/remote 产品路径）：`app/api/webui/auth_routes.py` + `app/services/webui/auth_service.py` — admin 密码 + `myrm_webui_session` Cookie；与 CP 邮箱登录（sandbox 前端构建）分离。

- **禁止**：server `app/` 运行时读取 `BASIC_*`/`LITE_*`/隐式 searxng fallback。
- **Subagent 超时**：唯一来源 `app/config/subagents/*.yaml`（无 env policy 覆盖层）。
- **Control Plane 遥测**：`ControlPlaneSettings` + `ContextCompactionTelemetrySettings`（`settings.control_plane` / `settings.context_compaction_telemetry`）。
- **[T] 测试密钥**：仅 `tests/support/test_secrets.py`（server `env_loader` 不读取 `.env.test`）。

### 0.07 Security Center（GitHub 供应链 + 平台审计）

- **API**：`app/api/security/router.py` — `/api/v1/security/dashboard`、`/setup-hints`、`/rate-limits`、`/audit/*`（与 Agent 工具策略 `allowlist`/`profiles` 等同包不同域，见 `app/api/security/_ARCH.md`）。
- **合并逻辑**：`app/services/security/merged_dashboard.py` — sandbox 时 CP internal 告警 + 可选 GitHub PR/SBOM；`data_source=merged` 仅当 GitHub 补充有数据。
- **用户仓库配置**：Omni-Config 键 `securityDashboardSettings.monitoredGithubRepos`（≤3），`dashboard_settings.py` 读取；零告警时仍可拉 Dependabot PR。
- **SaaS ingest**：闭源 CP `security_webhook_routes.py`（GitHub webhook → `SecurityAggregator`）；Server 经 `cp_security_dashboard.py` 拉取，**不**在 OSS server 实现多租户。
- **前端**：`myrm-agent-frontend/src/app/security/page.tsx`；导航快捷入口 `NavBar` → `/security`。

### 0. 零开销本地模式 (Zero-Overhead Local Mode)

在 Agent-in-Sandbox 架构下，为了保证本地桌面（Tauri/Sidecar）环境的极致轻量化：

- **依赖分层**：主依赖 `httpx`、`filelock`（cron/多进程锁）、`tenacity>=9.1.4`（`vercel_client`）、`myrm-agent-harness[…,retrieval,…]`（Matrix SOCKS 走 `aiohttp` + extra `aiohttp-socks`）。可选 extra：`matrix` / `matrix-e2ee` / `data-viz`。`[dependency-groups] sandbox`：`prometheus-fastapi-instrumentator` / `granian` / `slowapi`。本地 Matrix：`uv sync --extra matrix`（E2EE 再加 `--extra matrix-e2ee`）。`myrm setup` / `uv sync` 单层安装。
- **执行运行时绘图栈隔离**：`matplotlib`/`pandas` 收敛到 `[project.optional-dependencies] data-viz`，仅随镜像 `--all-extras` 安装，本地精简安装不引入；CJK/Emoji 字体与默认字体配置（`matplotlibrc`，经 `MATPLOTLIBRC` 加载）则烤入 `Dockerfile`（只读 rootfs + 非 root 无法运行时安装）；字体缓存经 `MPLCONFIGDIR=/tmp/matplotlib` 重定向到可写 tmpfs，避免只读 rootfs 下每个无状态执行子进程重建字体缓存。共同保障浏览器截图 / PDF / 数据图表的中日韩渲染保真。
- **动态监控隔离 (Metrics)**：`/metrics` 路由、内存直方图、数据库连接池采集器在 **local 与 sandbox 默认均关闭**；仅当 `METRICS_ENABLED=true` 时启用（见 `app/core/monitoring/__init__.py` + `DeploymentCapabilities.default_metrics_enabled`）。
- **全链路追踪纯净化 (Tracing)**：依赖 Harness 层的 No-Op 降级机制，Server 层在本地模式下绝不初始化 OpenTelemetry SDK，彻底消除不必要的后台序列化与网络发送开销。

### 0.1 统一本地存储架构 (Unified Local Storage)

无论是 `local` 还是 `sandbox` 模式，Server 业务层默认使用 `LocalStorageBackend`（沙箱模式下指向 Control Plane 挂载的 Volume/PVC）。主路径不依赖 S3；`aioboto3` 仅用于可选远程备份（`app/services/memory/backup_remote.py` lazy import）及沙箱存储适配，未配置 S3 时不加载。

### 0.2 工业级单机并发安全 (Industrial-Grade Standalone Concurrency)

针对单机环境（Sandbox/Local）中可能存在的跨进程资源竞争，系统拒绝引入 Redis 等外部锁服务，转而采用 **OS 原生文件锁 (File Locks)** 实现「精钢级」并发安全：

- **跨进程互斥**：使用 `fcntl.flock` 实现内核级文件锁，确保多个 Server 实例或 Cron 进程在访问同一技能文件、SQLite WAL 日志时，具备微秒级的互斥性能且零基础设施开销。
- **无感适配**：通过 `StandaloneLockProvider` 桥接 `myrm-agent-harness` 锁协议，实现业务逻辑对多进程安全性的透明支持。

### 0.3 LLM 前缀缓存优化 (LLM Prefix Caching Optimization)

为了极致降低持续进化的 LLM 调用成本（减少 90%+ 成本及延迟）：

- **稳定前缀架构**：遵循「指令首发、数据居中、采样垫后」的 Prompt 构建原则，确保 Agent 优化指令等高频、大体积文本在 LLM 侧被高效识别为 **Prompt Cache Prefix**。
- **冷热数据分离**：在 `SkillOptimizer` 提示词中，将高变动的性能遥测数据（Success Rate, Tokens）放置在 prompt 尾部，从而最大化静态指令集的缓存命中率。
- **Context Health 聚合**：`app/api/statistics/context_health.py` 将 Chat 压缩元数据、Message usage 与 Harness task metrics 聚合为 Session Analytics 的 context health，包含 cache-TTL 剪枝、归档写入/复用、恢复 requested/allowed/blocked outcome、blocked ratio、恢复范围提示、自适应剪枝退让和 provider-aware cache retention。
- **入账 Human 路由一致性**：`app/core/utils/delivery_provenance.py`。Server 在 GeneralAgent **`stream_pipeline`：INFO 记下 `general_agent_delivery_labels`** 后以 `apply_delivery_banner` 落横幅；FastLane/DeepResearch（`general_agent/streaming`，`apply_general_agent_pipeline_banner`/`params.channel_name`）；Fast Search 通过 `prompt_mode="search"` 统一走 GeneralAgent 路径（等价 `web_chat`→GUI 横幅）；IM `prepend_plain_banner`；Headless wakeup（`services/agent/wakeup_handler.py` 将 **`channel_name=headless_wakeup`** 且 **`memory_channel_id` 缺省时锁 `web_chat`**，防记忆命名空间漂移）。`web_chat` 仍映射 http_gui/browser_sse；`cron`/`eval`/其它见 `resolve_general_agent_pipeline_labels`。

### 0.4 进化驱动型技能观测 (Evolution-Driven Skill Observation)

为了支持 Agent 技能的持续迭代与安全灰度：

- **无感上下文追踪 (Context Tracking)**：利用 `ContextVar` 实现跨 Harness 和 Server 的版本号随路追踪，确保每一笔请求的来源版本可回溯、可审计，性能损耗控制在微秒级。
- **零风险影子验证 (Shadow Testing)**：`ShadowTester` 引擎是纯粹的"执行+比对"引擎，利用沙箱的 `isolated_mode` 在后台静默执行候选版本，返回 `ShadowTestResult` 而不操作 DB。所有副作用在影子模式下均被自动拦截或 Mock。
- **托管队列 (Managed Queue)**：`ABTestManager` 作为中枢控制器，通过 `asyncio.Queue` + worker pool 统一管理影子测试的调度、重试（指数退避）、优雅关机，替代裸 `create_task` 的不可靠方式。
- **智能判官 (Result Comparator)**：Harness 层提供 `ResultComparator` Protocol + `StructuredComparator`（JSON 结构化 + Jaccard 文本相似度，零 LLM 成本）；Server 层实现 `SemanticComparator`（基于原始分数均值判断是否触发 LLM 语义判定，仅在 local_avg < 0.7 且 > 0.1 的中间地带调用 LLM）。
- **侧边比对证据链 (Side-by-Side Evidence)**：`ShadowSampleModel` 记录真实请求下的输入输出快照，包含 `similarity_score` 和 `diff_summary`。前端 `SkillQualityGuardian` 展示 SimilarityBar、diff 摘要、可展开 JSON diff，支持数据驱动的版本晋升。
- **原子计数与保留策略**：`atomic_increment_sample_size` 确保并发安全；分歧样本 100% 保留，一致样本 20% 采样；`cap_samples_per_test` 优先保留分歧样本；`cleanup_old_samples` 按 TTL 清理已完成测试。
- **Auto-Promote**：样本量达标 + 成功率 > 95% + 延迟无回归时自动转正，通过 EventEmitter 通知前端。
- **技能免疫闭环**：订阅 Harness `SkillFailureEvent`，在 Server 单机业务层完成运行时失败分类、幂等去重、修复提案生成与 GUI 审批落地，Control Plane 不参与技能业务。

### 0.5 Shared Context 共享记忆治理 (Shared Memory Governance)

借鉴 Hermes 的灵活记忆理念但保留 OpenClaw 式边界控制，Server 产品层提供 Shared Context：

- **产品层治理**：`app/services/memory/shared_context.py` 管理共享上下文、agent/channel/cron/conversation/task 绑定和写入提案；Harness 只接收 `shared:<context_id>` namespace，不感知 team 概念。
- **运行时解析**：Web、Channel、Cron、Eval 入口在创建 Agent 前解析 Shared Context 绑定，通过 `memory_shared_context_ids` 下传给 GeneralAgent，再由 memory adapter 追加到 recall namespaces。
- **写入安全**：共享记忆默认走 proposal_required 流程，批准后由 `SharedContextProposalMaterializer` 幂等写入对应 shared namespace，并携带 proposal/source 审计元数据；私有记忆仍写入 agent/channel/conversation/task 边界，避免共享上下文污染个人记忆。
- **纠错自动传播**：`callbacks.py::make_correction_propagation_callback` 在会话结束时检测 `FeedbackSignal.NEGATIVE`，通过 LLM 提取纠错摘要，以 `chat_id:content_hash` 作为 proposal source_id 实现幂等 dedup，自动为绑定的 SharedContext 创建 `correction_propagation` 类型写入提案。当 SharedContext policy 的 `correction_auto_approve=true` 时自动物化，否则进入人工审批流程；前端 pending toast 可跳转 Memory Shared Context Inbox。实现"纠正一个 Agent，所有 Agent 同步学习"。
- **Goal 完成决策归档**：`goal_registry.py::ServerGoalManager._consolidate_decisions_on_completion` 在 Goal COMPLETE 时从 `planner_` 前缀 Planner 存储读取 `DecisionRecord`，通过 `_resolve_shared_context_ids_for_goal`（agent_id + web_chat + conversation_id）解析绑定，为 SharedContext 创建 `goal_completion` 写入提案（同 goal_id 幂等 dedup）；当 policy 的 `goal_completion_auto_approve=true` 时由 `SharedContextProposalMaterializer` 自动物化并推送 `memory_operation` toast，否则进入 Proposal Inbox；失败时发布 `goal_completion_consolidation_failed` event。实现跨 Agent 架构决策持久共享。
- **历史证据提升**：`app/services/memory/shared_context_history.py` 复用 ChatService 的 FTS5 会话搜索，把用户选中的历史消息转换为可审批写入提案，而不是直接污染共享记忆。
- **历史会话召回**：`app/services/chat/conversation_search_service.py` 实现 Harness `ConversationSearchProtocol`，按当前 `chat_id` 排除本会话，并用 Server scope policy 和 `agent_id` 做硬过滤/排序加权；FTS5 命中来自消息段索引并同时带出 `compacted_summary`，空查询返回最近会话列表，semantic 路径必须经 Server 索引 hydration 后才返回可核验 snippet/source_ref，并与 FTS/recent/消息级历史搜索共享 active、excluded、scope/source/fork lineage 过滤。
- **外部记忆导入治理**：`app/services/memory/import_sessions.py` 持久化 dry-run 审查会话、payload hash、过期时间、normalized data 和 plan hash；确认导入只接受 `dry_run_id` 并校验计划一致性，写入时追加 `import_batch_id/import_source/import_payload_hash/import_item_id` 元数据，并把实际写入 id 映射为 item-level transaction ledger。服务端记录 profile 导入前后 revision snapshot，确认后自动运行内容安全 Memory Doctor 并回写迁移来源；回滚前提供 dry-run 摘要和 profile revision 覆盖风险提示，确认后先持久化 rollback journal，再按 `dry_run_id` 或 `import_batch_id` 删除本批次 semantic/episodic/conversation/procedural 记忆并恢复 profile，启动预热会恢复未完成回滚，回滚响应返回 deleted/missing/forbidden/failed refs 和完整性状态，已完成审查会话按保留窗口清理。Command Center 通过 adapter registry 展示 native-json/agentmemory 等来源状态、最近导入批次、自动诊断状态、导入审查清理指标、导入后验证建议和回滚预演入口，metadata-only plane summary 暴露导入回滚健康计数供控制平面读取。

### 0.6 全域动作空间与准确度引擎 (Global Action Space & Decision Accuracy Engine)

为了彻底解决大模型在面临海量工具时的“幻觉率上升”问题，系统实现了跨三层的架构级收束机制，将“配置大而全”的陷阱转变为**“动作空间越小，决策准确率越高”**的实战理念：

- **Harness 层的协议与算力下沉**：不使用粗糙的“Token计数”来评估认知负载。原生内嵌了 `ActionSpaceProfiler` 协议，动态解析所有传入 Agent 的工具 JSON Schema（参数数、嵌套层级），科学地计算出 `ActionSpaceComplexityScore` (ASCS)，作为评估该 Agent 是否容易出现幻觉的标准基准。
- **Harness 层的前缀缓存硬核保护**：动态外部工具（特别是不可控的 MCP 工具库）绝不能污染高频的 Core Prefix Cache。通过 `tool_layers.py` 严格的层级分发，所有 MCP 和第三方不稳定的技能被强行分配到 `ToolLayer.EXTENDED`。这就保证了前面的 System Prompt 和 File Read/Write 等高频工具永远处在提示词的第一梯队，使大模型提供商的 Prefix Cache 命中率能稳死在 100%。
- **Server 层的动态驱逐风控**：Server 新增 `idle_tool_pruner` 异步任务，借力现成的 `ApprovalRegistry`。当系统探知用户配置了巨量外部工具但在近 30 轮对谈中未调用时，主动挂载一条闲置工具驱逐提案。将大盘维护变为友好的“一键点击净化”，真正意义上提升单点 Agent 的业务稳定性。

### 0.7 Public Ingress Orchestration (公网入站流量编排)

为了彻底解决本地桌面用户无法使用被动触发渠道（如 Twilio SMS、LINE、WeCom Webhook、外部 Cron 回调）的网络死胡同问题：

- **控制平面注入 (SaaS 模式)**：在控制平面调度沙箱时，自动通过 `CP_PUBLIC_INGRESS_URL` 环境变量向 Server 注入租户专属公网域名。
- **动态 Resolver API (单机模式)**：业务层提供 `/api/v1/system/ingress-url` 端点。优先级：`CP_PUBLIC_INGRESS_URL` → 运行中 Quick Tunnel 运行时 URL → `UserConfig.personalSettings.publicIngressBaseUrl`。实现一处配置，全局 Webhook 生成生效。
- **纯粹的业务层分离**：Webhook 的公网路由补全纯属业务逻辑表现，绝不污染底层 Harness 的执行引擎。
- **前端闭环与联通测试**：Settings > System 合并 Quick Tunnel 与 Public Ingress；隧道启动后自动写入 `publicIngressBaseUrl` 并支持 `/api/v1/health` 探活。
- **Quick Tunnel（本地/WebUI）**：`app/core/infra/tunnel/` 为唯一 cloudflared 进程宿主；Tauri 仅注入 `CLOUDFLARED_PATH` 并委托 Server API。

### 0.8 统一工具网关状态代理 (Unified Tool Gateway Proxy)

为了实现 SaaS 多租户架构下的中心化工具调度计费（API Key 托管、WU 计费）与 Local BYOK（Bring Your Own Key）的无缝切换：

- **前端架构收敛**：通过 `ToolCapabilitiesSection` 统一管理 Gateway Token 与 Local API Keys。前端调用 Server `/api/v1/system/gateway/health` 检查可用性。
- **Server 透明代理**：Server 层自身**不解析也不缓存**用户的网关凭证。`/api/v1/system/gateway/health` 端点负责将请求（携带前端传入的 PAT）穿透转发至 Control Plane 的 `/v1/tool_relay/health`。
- **Harness 弹性回退**：底层执行引擎在解析到 `ToolGatewayConfig` 时，优先使用网关转发 HTTP 请求。如果遭遇 401 或 WU 不足，将静默 fallback 至用户在前端配置的 Local API Key，实现业务高可用。

### 1. Core 模块独立性

`app/core/` 是一个独立的包，未来会拆分为独立项目：

- ✅ Core 内部模块可以相互引用
- ✅ Core 对外暴露公共 API
- ❌ Core 不应引用 Core 外部的资源

### 2. 分层依赖

```
api/ → services/ → ai_agents/ → core/
                              ↘ toolkits/
```

- 上层可以依赖下层
- 下层不应依赖上层
- 同层之间通过接口通信

### 3. 错误处理

使用框架层的 `ToolError` 进行统一的工具错误处理：

```python
from myrm_agent_harness.utils.errors import ToolError

# 简单用法
raise ToolError(
    message="Container exited with code 255",
    user_hint="Check if the return value is JSON serializable"
)

# 完整用法（诊断信息 + 修复建议）
raise ToolError(
    message="Container exited with code 255",
    user_hint="You may have used a return value with an unclear structure.",
    diagnostic_info={
        "error_category": "execution_failure",
        "exit_code": 255,
        "last_output": "..."
    },
    recovery_suggestions=[
        "Check if the return value is JSON serializable",
        "Verify the command syntax is correct",
        "Try running the command with simpler arguments"
    ],
    error_code="SANDBOX_EXIT_255"
)
```

---

## 技术栈

- **运行时**: Python 3.13
- **Web 框架**: FastAPI + uvicorn (uvloop)
- **AI 框架**: LangChain + LangGraph
- **LLM 适配**: LiteLLM（多模型支持）
- **包管理**: UV

---

## 更新日志

| 日期       | 更新内容             | 更新者 |
| ---------- | -------------------- | ------ |
| 2024-12-22 | 创建分形文档系统规范 | AI     |

## 可视化桌面流 (Visual Desktop Streaming)

为了提供“直播 AI 操作”的极致用户体验，Server 镜像内集成了完整的图形化和推流基础设施：

- **基础设施**：`Dockerfile` 中安装了 `xvfb` (虚拟显示器)、`fluxbox` (窗口管理器)、`x11vnc` (VNC 服务) 和 `websockify` (WebSocket 代理)。
- **启动编排**：`docker/entrypoint.sh` 监听 `VISUAL_DESKTOP=1` 环境变量。当开启时，按顺序拉起上述服务，将 `DISPLAY=:99` 的画面暴露在 `6080` 端口的 WebSocket 上。
- **全栈打通**：配合 Harness 层的 `browser` 工具包（自动关闭无头模式并连接到 `:99`）和前端的 `noVNC` 客户端，实现端到端的可视化桌面直播。
