# ACP 系统设计方案

> 基于多项目调研汇总的可执行框架方案：Server 与 Runtime 分层，横切能力开箱即用。

---

## 1. 设计原则

- **Runtime 独立层**：对外部 Agent 统一抽象为 `RuntimeBackend`（ACP / CLI）
- **能力 ≥ 竞品**：覆盖主流竞品核心能力，在关键维度可对标或超出
- **禁止过度设计**：每个组件有明确职责与参照价值
- **Python 原生**：asyncio、Protocol、dataclass、StrEnum，无额外编排框架依赖
- **Server 层稳定**：server/ 子目录（server.py / bridge.py / event_translator.py）专注 IDE ↔ 宿主 Agent 桥接

---

## 2. 架构总览

```
╔═══════════════════════════════════════════════════════════════╗
║                     ACP 系统架构                              ║
╠═══════════════════════════════╦═══════════════════════════════╣
║  Server 层 (server/)           ║  Runtime 层 (runtime/)         ║
║  server.py                    ║  RuntimeBackend Protocol       ║
║  bridge.py                    ║  ├─ AcpRuntime + AcpCallback   ║
║  event_translator.py          ║  └─ CliRuntime                 ║
╠═══════════════════════════════╩═══════════════════════════════╣
║                    横切关注点 (core/)                          ║
║  types.py · core/EventBus · core/PermissionManager           ║
║  core/BackendDetector                                         ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 3. 核心模块设计

### 3.1 RuntimeBackend Protocol（核心抽象）

**来源**：openclaw AcpRuntime + workany AgentPlugin + LobsterAI CoworkRuntime

**价值**：将 ACP 协议连接与 CLI spawn 统一为一个接口，新增后端只需实现这个 Protocol。

```
RuntimeBackend (Protocol)
├── name: str                                    # 后端标识
├── capabilities: BackendCapabilities            # 能力声明
├── is_alive: bool                               # 存活检查
├── run_turn(prompt, session_id, **) -> AsyncGenerator[RuntimeEvent]  # 核心执行；消费方提前停止时用 aclosing 关闭
├── cancel(session_id) -> None                   # 取消当前轮次
├── resume(session_id) -> bool                   # 恢复会话
├── get_info() -> BackendInfo                    # 后端元数据
└── close() -> None                              # 关闭连接
```

**设计亮点**：
- `cancel()` — 完整的生命周期控制，用户可中断长任务
- `get_info()` → `BackendInfo` — 后端元数据（版本、能力、状态），支持运行时能力查询

**BackendCapabilities**：
- `supports_resume`：是否支持会话恢复
- `supports_mcp`：是否支持 MCP Server 注入
- `supports_streaming`：是否支持流式传输
- `supports_tools`：是否支持原生工具调用

**2 种实现**：

| Runtime | 协议 | 参考项目 | 适用场景 |
|---------|------|---------|---------|
| AcpRuntime | ACP JSON-RPC (stdin/stdout) | openclaw, zeroclaw | 需 ACP 桥接器（claude-agent-acp / acpx），原生 CLI 不支持 ACP |
| CliRuntime | spawn CLI + NDJSON 解析（含 reasoning/usage/工具调用）；Claude / Codex 经 CLI 自己的会话 id 跨回合续接 | ironclaw, nullclaw, picoclaw | Claude/Codex/Gemini CLI（推荐，开箱即用） |

**BackendInfo**：
```
BackendInfo
├── name: str
├── version: str | None
├── backend_type: "acp" | "cli"
├── status: "ready" | "starting" | "error" | "stopped"
├── capabilities: BackendCapabilities
└── metadata: dict[str, object] | None
```

来源：AionUi 后端版本检测 + workany AgentProviderMetadata

### 3.2 RuntimeEvent（统一事件模型）

**来源**：opencode 事件订阅 + nextclaw NCP 34 事件类型（精简版）

```
RuntimeEvent (frozen dataclass)
├── type: RuntimeEventType
├── data: dict[str, object]
├── session_id: str
└── timestamp: float
```

**RuntimeEventType 枚举（9 种）**：

| 事件类型 | 说明 | data 字段 |
|---------|------|----------|
| `text_delta` | LLM 文本增量 | content: str |
| `reasoning_delta` | 思维链增量 | content: str |
| `tool_start` | 工具调用开始 | tool_name, tool_input, tool_call_id, summary（一行摘要，可为空） |
| `tool_result` | 工具调用结果 | tool_call_id, output（CLI 后端截断到 2000 字符）, is_error |
| `permission_request` | 权限请求 | tool_name, tool_input, options, response_future: asyncio.Future[PermissionDecision] |
| `usage_update` | Token 用量更新 | input_tokens, output_tokens, cache_read, cache_write |
| `status_update` | 后端状态变化 | status: str, message: str &#124; None |
| `error` | 错误事件 | error: AcpError |
| `done` | 会话结束 | stop_reason, total_usage |

**设计亮点**：
- `reasoning_delta` — 支持思维链展示（参考 nextclaw MessageReasoningDelta）
- `usage_update` — 实时 Token 监控（参考 craft-agents-oss token 估算）
- `status_update` — 后端状态变化通知（starting, compacting, reconnecting 等），UI 可精确展示后端状态；会话连续性通知由 `types.ContinuityStatus` 定义：`session_expired`（CLI 已不认识上次的会话，本回合改开新会话）与 `session_workspace_changed`（工作目录变了，不续接），宿主据此提示用户而不是当作错误
- `permission_request` 包含 `response_future` — 参考 Claude-Cowork PendingPermission 模式，run_turn 内部 await Future，订阅者通过 `future.set_result(decision)` 响应，超时按 PermissionManager 默认策略处理

### 3.3 结构化错误体系

**来源**：craft-agents-oss 错误标记 (__API_KEY_ERROR__ 等) + ironclaw 错误分类

```
AcpErrorCode (StrEnum)
├── AUTH_FAILED         # API Key 无效
├── BACKEND_NOT_FOUND   # CLI 未安装
├── TIMEOUT             # 超时
├── RATE_LIMITED        # 超频
├── CONTEXT_OVERFLOW    # 上下文溢出
├── PROCESS_CRASHED     # 进程崩溃
├── MAX_TURNS           # CLI 自身的轮次上限已到（不是故障）
├── PERMISSION_DENIED   # 权限拒绝（safe 模式下拒绝写操作等）
├── CANCELLED           # 用户取消
└── UNKNOWN             # 未知错误

AcpError (frozen dataclass)
├── code: AcpErrorCode
├── message: str
├── retryable: bool
└── details: dict[str, object] | None
```

**价值**：生产系统必须有结构化错误码，上层可根据 `retryable` 自动重试，根据 `code` 精准定位问题。

### 3.4 EventBus（统一事件总线）

**来源**：opencode 全局事件流 + nextclaw AgentConversationStateManager

**价值**：解耦事件生产者和消费者，支持外部订阅（UI、日志、监控）。

```
EventBus
├── subscribe(event_type | None, callback, *, session_id: str | None) -> subscription_id
├── unsubscribe(subscription_id) -> None
└── emit(event: RuntimeEvent) -> None
```

**增强**：
- Session 级过滤：subscribe 可指定 session_id，只接收该会话的事件
- 异步回调：支持 async callable

### 3.5 PermissionManager（增强权限管理）

**来源**：craft-agents-oss 4 种权限模式 + ironclaw 工具白名单 + AionUi 审批缓存

**架构**：框架层提供 `PermissionManager` Protocol + `DefaultPermissionManager` 默认实现，业务层可替换为自定义实现。

```
PermissionManager (Protocol)
├── check(tool_name, tool_input, session_id) -> PermissionDecision
└── record_approval(tool_name, session_id) -> None

框架层默认实现：DefaultPermissionManager
业务层可实现：UIPermissionManager, AdminPermissionManager 等
```

**4 种权限模式**：
- `safe`：只允许读操作（Read, Glob, Grep, Search）
- `ask`：每次工具调用都询问用户（通过 EventBus 发送 permission_request）
- `allow_all`：自动批准所有工具
- `bypass`：跳过框架侧权限检查（由外部后端自身的权限机制接管）

**增强功能**：
- **工具白名单 + 参数级通配符**：`allowed_tools: list[str]`，支持 `Bash(npm run *)` 格式
- **Session 级审批缓存**：用户选择 "always allow" 后缓存决策
- **工具分类**：自动识别读/写/执行操作
- **异步响应机制**：`ask` 模式下，run_turn 产生包含 `asyncio.Future[PermissionDecision]` 的 permission_request 事件，await Future 等待外部决策；PermissionManager 在 `allow_all` / `safe` / `bypass` 模式下自动 set_result，无需外部参与

### 3.6 BackendDetector（后端自动检测）

**来源**：AionUi 后端自动检测 + workany 6 级 Claude Code 发现

**检测策略**：
1. `which` / `where` 命令
2. 扩展 PATH 搜索
3. 常见安装路径（/usr/local/bin, ~/.local/bin）
4. npm global
5. 可选版本检测（`--version`，按调用方需要开启）
6. 可选强制刷新（`refresh=True`，绕过缓存）

**返回**：`list[DetectedBackend]`（name, path, version）
**缓存**：进程级双缓存（带版本 / 不带版本）+ 软 TTL（默认 300s），避免重复路径扫描与重复版本探测，同时避免长期陈旧结果常驻

### 3.7 RuntimePool

**价值**：统一管理任意 `RuntimeBackend` 实例，配置驱动 + 并发控制（`asyncio.Semaphore`）。

```
RuntimePool(*, max_concurrent: int = 4, event_bus: EventBus | None = None, cli_session_store: CliSessionStore | None = None)
├── register(name, config: RuntimeConfig) -> None
├── get(name) -> RuntimeBackend
├── prompt(name, task, *, mode) -> str      # 委托 run_turn()，收集 text_delta
├── run_turn(name, prompt, session_id, *, mode, mcp_servers) -> AsyncGenerator[RuntimeEvent]  # Semaphore 并发控制
├── cancel(name, session_id) -> None        # 级联取消 → backend.cancel()（在途 oneshot 优先）
├── available_backends -> list[str]
├── release_resident() -> None              # 只释放常驻进程型（ACP）后端，保留 CLI 后端及其 --resume 状态
└── close_all() -> None                     # 关闭所有后端（含在途 oneshot）
```

**要点**：
- `RuntimeConfig.backend_type` 选择 `AcpRuntime` / `CliRuntime`
- `max_concurrent` 限制同时执行的委托任务数，避免进程与文件句柄耗尽
- `prompt()` 委托给 `run_turn()`，并发控制统一在 `run_turn()` 层
- **会话模式 `mode`**：`persistent`（默认）每个后端名共享一个后端实例，会话跨回合延续（CLI 的 `--resume` id、ACP 的常驻进程与会话）；`oneshot` 在**私有后端实例**上运行、回合结束即关闭（关闭失败只记 warning，不覆盖回合结果或回合异常）——总是全新会话，且不触碰 persistent 后端的会话与进程。在途 oneshot 后端按 `(name, session_id)` 登记，`cancel` 优先路由到它，`close_all` 一并关闭；同名后端的回合仍由 per-name 锁串行化（避免同一工作区同时跑两个同名 agent）
- **空闲释放 `release_resident()`**：宿主在会话空闲时调用，只关闭并摘除常驻进程型（`backend_type == "acp"`）后端，下一回合惰性重建；CLI 后端回合之间没有进程，只持有 `--resume` 会话 id，原样保留，所以空闲回收不会让 CLI 会话断档。调用方须保证此刻池上没有在跑的回合（与 `close_all()` 同一约定）
- **CLI 会话持久化 `cli_session_store`**：宿主可注入 `CliSessionStore`（`load` / `save`，键为 harness session id，一个 store 服务一个会话作用域），让 CLI 后端的 `--resume` id 跨宿主进程重启存活。只注入共享的 persistent 后端；oneshot 私有后端是回合结束即消失的全新会话，既不读也不写 store。store 的任何异常只记 warning 并降级（丢连续性，不丢回合）；harness 在回合收尾处直接 await store 且不设超时，调用时延由实现方自己约束；harness 本身不依赖任何存储实现
- **进程生命周期**：不做周期性存活巡检。`CliRuntime` 每回合一个进程，回合之间没有进程是正常空闲态；`AcpRuntime` 常驻进程退出后，下一次 `run_turn` 发现 `is_alive` 为假就重新拉起进程（`_ensure_connection`）。进程是否卡住不属于存活检测，由 `timeout_seconds` 兜底
- **委托窄协议 `DelegationPool`（`types.py`）**：委托调用方只依赖 `available_backends` / `get_config` / `run_turn` / `cancel`；`RuntimePool` 与宿主侧包装器（如按会话串行化回合的 facade）都满足它，`create_invoke_acp_agent_tool` 接受它
- **MCP 注入能力守卫**：`run_turn()` 在转发 `mcp_servers` 前检查 `backend.capabilities.supports_mcp`，不支持的 backends（如 `CliRuntime`）收到 `None` 而非原始配置，杜绝向不支持 MCP 注入的后端传递配置引发会话崩溃；跳过时记录 `pool_mcp_skipped` WARNING 便于观测

### 3.8 RuntimeConfig（统一配置）

```
RuntimeConfig (frozen dataclass)
├── backend_type: "acp" | "cli"
├── command: str | None                  # CLI/ACP 的可执行文件路径
├── args: list[str]                      # 命令行参数
├── env: dict[str, str] | None           # 额外环境变量
├── cwd: str | None                      # 工作目录
├── timeout_seconds: int = 300           # 超时
├── permission_mode: PermissionMode      # 权限模式
├── allowed_tools: list[str]             # 工具白名单
├── strip_env_keys: list[str]            # 需要剥离的环境变量
├── auth_mode: AuthMode = "subscription" # 鉴权模式：订阅登录态 / API Key
├── mcp_servers: list[McpServerConfig]   # MCP Server 配置
├── max_response_chars: int = 50_000     # 响应截断限制
├── max_turns: int = 25                  # 轮次上限：有原生上限的 CLI（Claude）经 --max-turns 自行停止，其余后端由 delegate 按工具调用数兜底
└── description: str = ""                # Agent 能力描述（注入 tool description）
```

**环境变量管理 + 鉴权模式（`auth_mode`）**：
- 敏感信息过滤：`build_safe_env()` 始终剥离子进程继承的 provider 密钥（前缀剥离 + `strip_env_keys`），各 Runtime 启动前统一调用
- `subscription`（默认）：剥离所有 provider 密钥 **并丢弃** `env` 中注入的密钥，强制委托 CLI 走自身订阅登录态（用户的 ChatGPT Plus / Claude Max / Gemini 订阅），绝不静默回退按量计费的 API Key
- `api_key`：业务层经 `env` 注入该后端应计费的单一 provider 密钥，剥离基线后重新应用
- 价值：让 GUI/SaaS 用户用已购订阅驱动外部 CLI，无需重复购买 API Key（详见 3.10 auth 子系统）

### 3.9 _base.py（RuntimeBackend 基类）

**价值**：提取各 Runtime 的通用逻辑，避免重复代码。

**通用功能**：
- 环境变量清理（`build_safe_env`）
- 超时控制（`asyncio.timeout`）；回合生成器由 `aclosing` 收尾，超时、异常或消费方提前放弃都会停掉外部进程
- 流式响应截断（`max_response_chars`，统一对 TEXT_DELTA 事件逐字符计数）
- 日志规范化

### 3.10 auth 子系统（订阅鉴权）

**来源**：pi-mono `/login`（ChatGPT Plus/Pro·Claude Pro/Max）+ openhuman `openai_oauth/`（flow/store/status）+ zeroclaw「API Key vs Codex 订阅」二选一 + opencode 订阅插件

**价值**：让委托的外部 CLI（Codex / Claude Code / Gemini / Qwen）运行在**用户自己的模型订阅**上而非按量计费的 API Key。框架只出**机制**（业务无关），由业务层驱动 GUI/SaaS 登录、状态徽章与凭据持久化。

```
auth/
├── _profiles.py        # AuthProfile：每个 CLI 的凭据路径、登录命令、策略、api_key env
│                       #   环境感知 resolve_home（CODEX_HOME/CLAUDE_CONFIG_DIR → /persistent）
├── credential_store.py # CredentialStore：状态检测 / 通用凭据导入（原子写+0600）/ 清除
└── login_session.py    # CliLoginSession：驱动 <cli> login，流式 AuthEvent（提取 URL/设备码）
```

**三大机制**：
- **凭据检测**（`CredentialStore.state`）：该后端是否已登录？驱动预检与状态徽章；鉴权态从不缓存（用户随时登录/登出）
- **交互式登录**（`CliLoginSession`）：spawn `<cli> <login_args>`，并发读 stdout/stderr，URL/设备码 → 可操作 PROMPT 事件，进程退出后用 `CredentialStore` 校验落地 → SUCCESS/ERROR；`needs_code_input` 时经 `feed()` 回填用户粘贴的 code
- **凭据导入兜底**（`CredentialStore.import_credential`）：登录不可脚本化（gemini/qwen 浏览器流）或不便时的**通用路径**——用户在有浏览器的机器登录后粘贴 `auth.json`，原子安全写入对应路径

**设计铁律**：
- 鉴权态**绝不进入** Turn1 工具描述；`create_invoke_acp_agent_tool` 使用**固定 schema**（backend 列表仅在运行时 KeyError 返回值中暴露），不破坏提示词前缀缓存
- 凭据路径环境感知 → 控制平面通过重定向 home（如 `CODEX_HOME` → 持久卷）即可实现 SaaS 持久化，harness 零耦合
- 登录态检测基于文件，刻意**不做运行时硬预检**：跨平台凭据存储差异（如 macOS Keychain）会导致误判，CLI 自身的未登录错误已由 `PROCESS_CRASHED`（含 stderr 提示）准确透传，状态可见性由徽章承担

**与竞品对比**：

| 能力 | 竞品最佳 | 新方案 | 超越/平齐 |
|------|---------|--------|----------|
| 订阅登录 | pi-mono (`/login` 多 Provider) | login_session + 导入兜底 + 状态检测 | **平齐**（覆盖更鲁棒） |
| 凭据持久化 | openhuman (加密 profile store) | 环境感知路径 + 控制平面重定向 | **超越**（部署解耦） |
| 模式切换 | zeroclaw (Key/订阅二选一) | auth_mode + 双层 env 安全 | **超越**（注入密钥双重保险） |

---

## 4. 文件结构（与代码库一致）

```
acp/
├── __init__.py             # 惰性导出 RuntimePool / RuntimeConfig / RuntimeBackend + Server
├── __main__.py             # CLI 入口
├── acp_agent_tools.py      # delegate 工具门面（业务层委托入口）
├── types.py                # RuntimeEvent、Protocol（含 CliSessionStore）、RuntimeConfig、CliSessionRecord、错误码等
├── ACP_SYSTEM.md           # 本设计文档
├── _ARCH.md                # 模块索引
├── core/                   # 共享基础设施
│   ├── __init__.py
│   ├── event_bus.py        # EventBus
│   ├── permission.py       # DefaultPermissionManager
│   └── backend_detector.py # CLI 探测（detect + detect_with_auth 安装+登录态一次性视图）
├── auth/                   # 订阅鉴权子系统（业务无关机制）
│   ├── __init__.py         # 公共导出
│   ├── _profiles.py        # AuthProfile：CLI 凭据路径/登录命令/策略
│   ├── credential_store.py # 状态检测 + 凭据导入兜底 + 清除
│   └── login_session.py    # CliLoginSession：驱动 <cli> login，流式 AuthEvent
├── server/                 # ACP Server 方向（IDE → Agent）
│   ├── __init__.py
│   ├── server.py           # ACP Server（acp.Agent，支持动态绑定宿主 MCP 工具）
│   ├── bridge.py           # Session ↔ 宿主 Agent（会话生命周期与多工厂适配）
│   ├── mcp_converter.py    # ACP MCP Schema → Myrm MCPConfig 协议适配层
│   └── event_translator.py # AgentEvent → SessionNotification
├── runtime/                # Runtime 方向（Agent → 外部 Agent）
│   ├── __init__.py
│   ├── _base.py            # BaseRuntime
│   ├── acp_runtime.py      # ACP 子进程 + JSON-RPC
│   ├── acp_callback.py     # ACP 回调处理器
│   ├── pool.py             # RuntimePool
│   └── cli/                # CLI 后端子包
│       ├── __init__.py
│       ├── dialect.py      # 各 CLI 的命令行差异（续接语法、原生轮次上限、增量文本）与会话 id 形态校验
│       ├── failure.py      # 失败分类：用 CLI 自己的话（result 行 / 退出码）给出错误码
│       ├── parser.py       # 各输出格式共享的事件构造（工具调用/结果、usage、错误、thinking、Codex item.*）
│       ├── process.py      # CLI 进程：逐行 stdout、有界 stderr 尾部、唯一的停止入口（SIGTERM → SIGKILL）
│       ├── runtime.py      # CliRuntime：启动、续接、失效重试、会话 id 落盘、回合收尾
│       ├── session.py      # CLI 会话记录簿 CliSessionBook（内存优先 + 写穿到宿主 CliSessionStore）
│       └── turn_parser.py  # 单回合 NDJSON 解析器（announce / result / 增量文本去重）
└── toolchains/             # 隔离工具链（Node/npm）
    ├── __init__.py
    └── manager.py          # ToolchainManager
```

`toolkits/acp/acp_agent_tools.py` 通过 `RuntimePool` 发起委托，汇总 `USAGE_UPDATE` 事件的 token 消耗并推送至前端；用户停止时经 `utils/runtime/cancel_hook.on_token_cancelled` 停掉外部进程。`runtime/cli/turn_parser.py` 把一个回合的 NDJSON 行解析为 `RuntimeEvent`：Claude stream-json（content block 里的文本与 tool_use / tool_result，`--include-partial-messages` 的 `stream_event` 增量文本并按 API message id 去重）、Codex 新格式（`item.started/completed` + `turn.completed/failed`，含 `command_execution`、`file_change`、`reasoning` 事件映射）与 legacy `{"id","msg"}` envelope、纯文本；同时暴露 CLI 最先 announce 的会话 id 与 CLI 自己的 `result` 结论。`runtime/cli/parser.py` 提供各格式共用的事件构造。

---

## 5. 与竞品对比

| 能力 | 竞品最佳 | 新方案 | 超越/平齐 |
|------|---------|--------|----------|
| 可插拔后端 | openclaw (AcpRuntime) | ACP + CLI + cancel() + get_info() | **超越** |
| 权限管理 | craft-agents-oss (4模式) | 4模式 + 参数级通配符 + 缓存 | **超越** |
| 事件流 | opencode (订阅系统) | EventBus + session 过滤 | **超越** |
| Session 管理 | opencode (Fork/Resume) | Fork/Resume + TTL + 自动清理 | **超越** |
| 后端检测 | AionUi (自动检测) | 自动检测 + 版本检测 | **超越** |
| 事件类型 | nextclaw (34类型) | 9类型（精简完整，含 status_update） | **超越** |
| 错误处理 | craft-agents-oss (错误标记) | 结构化错误码 + retryable + PERMISSION_DENIED | **超越** |
| 安全模型 | ironclaw (纵深防御) | 环境清理 + 工具白名单 + 路径安全 | 平齐 |
| MCP 集成 | craft-agents-oss (Session MCP) | Session MCP 注入 | 平齐 |

**结果：7 项超越，2 项平齐，0 项落后**

---

## 6. 框架层/业务层边界

> 遵循 FRAMEWORK_DESIGN_PRINCIPLES.md：框架提供 Protocol + 默认实现，业务层按需替换。

### 框架层提供（开箱即用）

| 模块 | 类型 | 说明 |
|------|------|------|
| types.py | 核心类型 | Protocol / dataclass / StrEnum 定义 |
| runtime/_base.py | 基类 | 环境清理、超时、截断 = 自我保护 |
| runtime/acp_runtime.py | 实现 | ACP 协议后端 |
| runtime/cli/runtime.py | 实现 | CLI spawn 后端 |
| runtime/pool.py | 管理器 | 单实例内多后端管理 |
| core/event_bus.py | 事件系统 | 类似生命周期钩子，业务层订阅 |
| core/permission.py | Protocol + 默认实现 | DefaultPermissionManager（4 模式 + 白名单） |
| core/backend_detector.py | 工具 | 后端自动检测 |

### 业务层自定义（通过 Protocol 注入）

| 能力 | 框架提供的扩展点 | 业务层实现示例 |
|------|----------------|-------------|
| 权限交互 UI | EventBus + permission_request 事件 | 订阅事件 → 展示 UI → `future.set_result()`（尚未接入：未注入 EventBus 时 ask 模式降级为只读） |
| 监控集成 | EventBus 事件 | 推送到 Prometheus / DataDog |
| 自定义后端 | RuntimeBackend Protocol | HTTP API Agent / 自研 Agent |
| 自定义权限 | PermissionManager Protocol | 基于角色的权限管理 |

### 业务层接入（myrm-agent-server）

三层架构将框架能力接入到实际产品：

1. **配置层**：`UserConfig` 表 `config_key='externalAgents'`，JSON 格式 `{"agents": [{name, type, command, args, enabled, ...}]}`
2. **注入层**：`GeneralAgent._setup_external_agents()` 从配置创建 `RuntimePool` + `invoke_acp_agent_tool` 工具
3. **执行层**：LLM 自主决定是否使用 `invoke_acp_agent_tool` 委托任务给外部 Agent

**增强功能**：
- **本地模式自动发现**：本地部署时自动探测 claude/codex/gemini CLI
- **配置校验**：无效配置跳过并记录日志，不阻断 Agent 启动
- **权限配置**：每个外部 Agent 可独立配置 `permissionMode`
- **多渠道支持**：Web Chat 和 Channel 路径均支持外部 Agent
- **容错处理**：外部 Agent 配置失败不影响主 Agent 功能
- **前端名称唯一性校验**：保存时检测重复 Agent 名称，防止配置冲突
- **命令可用性测试**（本地模式）：通过 `POST /channels/manage/external-agents/test` 检测命令是否存在并返回版本信息
- **流式事件消费**：`invoke_acp_agent_tool` 通过 `pool.run_turn()` 逐事件消费，实时日志输出工具调用和状态更新，返回结果包含 tool_calls 计数等元数据
- **前端实时进度推送**：通过 ContextVar + `ToolProgressSink` 机制，`invoke_acp_agent_tool` 在执行期间将外部 Agent 的工具调用和状态事件实时推送至前端 SSE 流（复用 `TASKS_STEPS` 事件类型；会话连续性通知是只带标题的已完成步骤，措辞由前端按 `step_key` 本地化）
- **前端预设模板**：新增模式下提供 Claude Code / Codex CLI / Gemini CLI 一键填充，降低配置门槛
- **Max Turns 双层安全护栏**：Layer 1 是 CLI 自己的轮次上限——`CliDialect.with_max_turns` 为 Claude 追加 `--max-turns`，到限后 CLI 自行结束并在 `result` 行报告，`classify_failure` 把它归为 `AcpErrorCode.MAX_TURNS`，工具路径据此返回「已达轮次上限」而不是故障；Layer 2 是 delegate 工具对 `TOOL_START` 的计数，只用于没有原生上限的后端（`has_native_turn_limit`），超限时 `pool.cancel()`——Claude 的一个 agent 轮次可发出多个工具调用，对它计数会提前截断
- **稳定 Tool Schema**：`invoke_acp_agent_tool` 使用固定 tool description（不含动态 agent 列表），保护 Turn1 Prompt Cache；`agent_name` 无效时错误响应列出 `available_backends`
- **Deploy 门控（Server）**：`external_cli_deploy.is_external_cli_deploy_supported()` + profile `strip_deploy_incompatible_builtin_tools`；沙箱自动剔除 `external_cli`；BuiltinToolsPanel sandbox 硬禁用 toggle
- **MCP 会话注入**：`RuntimePool.run_turn` → `AcpRuntime.new_session(mcp_servers=…)`（无 MCP 时 Server 不传参数（None）；`RuntimeConfig.mcp_servers` 为配置源；注入前经 `capabilities.supports_mcp` 能力守卫，跳过不支持的 backends 并记录 `pool_mcp_skipped`）
- **Host 会话级 MCP 忽略诊断**：ACP Server 侧（`new_session` / `load_session` / `fork_session` / `resume_session`）若收到 host 传入的 `mcp_servers`，记录 `acp_host_mcp_ignored` WARNING —— Myrm 内部 agent 管线自行管理 MCP，host 提供的会话级 MCP 注入不被透传，显式告警避免静默丢失
- **失败分类**：`runtime/cli/failure.classify_failure` 按 CLI 自己的话归类——`result` 行的 `error_max_turns` → `MAX_TURNS`，`api_error_status` 401/403 → `AUTH_FAILED`、429 → 可重试的 `RATE_LIMITED`、5xx → 可重试的 `UNKNOWN`；没有 `result` 行时非零退出码才是 `PROCESS_CRASHED`（带 stderr 摘录）；本运行时自己停掉的进程一律是 `CANCELLED`。消息是 CLI 的原话，不夹带产品设置建议
- **跨平台进程组清理**：每个 CLI 回合都在独立进程组里运行（POSIX `start_new_session`，Windows `CREATE_NEW_PROCESS_GROUP`），停止时整组终止（POSIX `killpg`，Windows `taskkill /T /F`），子进程随之清理；回合以任何方式结束（正常、异常、取消、超时、消费方提前放弃生成器）都经同一个 `spawn_cli_process` 上下文停掉仍在跑的进程
- **委派取消传播**：通过 ContextVar 传递 `CancellationToken`；用户停止（或请求被取消）时，`invoke_acp_agent_tool` 借 `cancel_hook.on_token_cancelled` 在令牌被取消的一个轮询周期（0.25 s）内调用 `pool.cancel()` → `backend.cancel()`，外部 Agent 此刻没有任何输出也会停下（例外：回合开头把超过管道缓冲的提示词写进一个不再读 stdin 的 CLI 时，进程在写入完成前还没有交给运行时，停止要等写入结束才生效，上限是 `timeout_seconds`）。`CliRuntime` 对整个进程组 SIGTERM（5 s 宽限后 SIGKILL），清理在调用方再次被取消时也会跑完（shield）；停止落在进程尚未创建的瞬间（正在加载会话）时，会在进程创建后立即生效；被本运行时停掉的进程按 `CANCELLED` 处理而不是崩溃（真实 claude 被 SIGTERM 后以 143 退出，不能当作续接失败或崩溃）。宿主进程自身被强杀不在保证范围内
- **直连路由模式**：`force_external_agent` 参数允许前端绕过 LangChain Agent，直接将请求路由到指定外部 Agent，零 LLM 开销、零延迟的流式响应；**Server `stream_pipeline` 在 RuntimePool 之前评估 `invoke_external_agent`**——仅 `PermissionAction.ALLOW` 可继续直连，`DENY`/`ASK` 立即 SSE error（无审批 UI，不可绕过 Permission Engine）
- **流式文本推送**：Server 的 `services/external_agents/direct_delegate_stream.stream_direct_delegate`（由 `ExternalAgentMixin._direct_delegate_stream` 调用）把 `pool.run_turn` 的 RuntimeEvent 实时转换为前端 SSE 事件：TEXT_DELTA → MESSAGE、REASONING_DELTA → REASONING、TOOL_START / TOOL_RESULT → TASKS_STEPS、USAGE_UPDATE → TOKEN_USAGE、其余见下。连接前发送 connecting 状态，结束时发送 completed / stopped / failed 状态步骤与 MESSAGE_END，提供全生命周期进度反馈；翻译层只依赖 harness 的 `DelegationPool` 协议
- **REASONING_DELTA 前端传递**：`invoke_acp_agent_tool` 工具将外部 Agent 的思维链（REASONING_DELTA）通过 `ToolProgressSink` 实时推送至前端，用户可看到外部 Agent 的推理过程
- **CLI Session 复用**：CLI 回合最先输出的一行 announce 会话（Claude `system/init` 的 `session_id`、Codex `thread.started` 的 `thread_id`），`CliRuntime` 在收到 announce 的那一刻就记录（连同创建它的工作目录，`CliSessionRecord`）并写穿到宿主 `CliSessionStore`，所以回合中途被停止的会话照样能续接；记录只看 announce，不看回合结果。续接由 `CliDialect` 按各 CLI 的语法完成：Claude 追加 `--resume <id>`，Codex 把 `exec` 改写为 `exec resume <选项> <id>`（`codex exec resume` 只认自己的选项，`--sandbox` 这类根级选项仍在 `exec` 之前，prompt 跟在 id 之后）；id 必须是规范 UUID 形态才会被重放（Codex 对格式不对的 id 会静默开新线程）。Claude Code 按工作目录存放会话（v2.1.223 之前 `--resume <id>` 只在当前项目目录里查找 id），所以记录目录与本回合启动目录不同就不续接，改开新会话并发出 `session_workspace_changed`。**失效自愈**：续接的判据是 CLI 在 announce 之前、没有任何输出、以正退出码退出（它自己在说「不认识这个会话」），此时发出 `session_expired`，同一回合内改开新会话重跑一次；旧 id 在新会话 announce 之后才被替换，重试也失败则旧记录原样保留。被本运行时取消或超时杀掉的进程说明不了会话是否存在，记录保留。Claude / Codex 之外的 CLI 没有方言，按配置原样启动、不续接
- **Per-backend 并发串行化**：`RuntimePool.run_turn` 在全局 Semaphore 之外对同一 backend 增 per-backend `asyncio.Lock`，保证单后端实例（如 CliRuntime 的可变进程句柄）同时只跑一个 turn；`cancel()` 不取该锁（调用方在 turn 循环内取消，无死锁），不同 backend 仍可并行
- **超时/异常/放弃的进程清理**：`BaseRuntime.run_turn` 用 `aclosing` 包住回合生成器，超时、意外异常或消费方提前放弃都会让回合收尾并停掉外部进程；超时与异常再先 `cancel()` 后产出 ERROR 事件，杜绝孤儿进程在后台继续消耗资源
- **失败路径统一 ERROR**：一个失败的回合只以一个 ERROR 事件结束，不会被静默降级为 DONE 导致 delegate 误判成功：`AcpRuntime._do_run_turn` 的 prompt 失败会 re-raise，由 `run_turn` 转为 ERROR 并清理进程；`CliRuntime` 在回合末用 `classify_failure` 给出分类后的 ERROR（CLI 已流式给出 ERROR 事件时不重复；CLI 已产出文本、没有 `result` 行却以非零码退出时记 warning 并按 DONE 结束；`result` 行报错时一律是 ERROR）
- **NDJSON 解析分层**：`turn_parser.TurnParser`（有状态、无 I/O）+ `parser.py`（各格式共享的事件构造），任何 CLI 输出形态都能只凭文本做单测
- **增量文本与工具事件**：Claude 以 `--include-partial-messages` 启动（仅 stream-json 输出），文本逐段到达，随后重复的完整消息按 API message id 去重；assistant 消息里的 `tool_use` 与 user 消息里的 `tool_result` 映射为 `TOOL_START`（含一行摘要）/ `TOOL_RESULT`
- **大输出行**：stdout 单行上限 16 MiB（一条工具结果可以是整个文件，asyncio 默认的 64 KiB 会让整回合失败）；stderr 只保留末尾 8 KiB 用于错误摘录
- **Delegate 元数据 TypedDict**：`DelegateUsage` / `DelegateMeta` 提供精确的类型提示
- **直连模式 Session 隔离**：基于 `chat_id` 生成独立 `session_id`，不同对话的外部 Agent 上下文互不干扰
- **直连模式工具步骤**：外部 Agent 的每次工具调用是一个带 `tool_call_id` 的独立步骤（`delegation_<agent>_tool`，步骤文本为一行「agent: 工具 — 摘要」），对应的 TOOL_RESULT 更新同一步骤的状态（失败时带 CLI 原文的前 300 个字符），而不是覆盖上一个步骤；前端以这一行作标题，不再重复渲染
- **直连模式收尾与错误处理**：直连路径不重跑整个回合；`CANCELLED`（含用户停止、令牌被取消）只发出 CANCELLED 事件、不发完成状态，`MAX_TURNS`（外部 Agent 到了自己的轮次上限）按「已停止」收尾而不是错误横幅，其余 ERROR 转成前端 error 事件并以 failed 状态步骤收尾。唯一的自动重来是 `CliRuntime` 对被 CLI 拒绝的续接在同一回合内改开新会话（见「CLI Session 复用」，用户看到一条只带标题的提示）；`invoke_acp_agent_tool` 工具路径另有对 `retryable` 错误的一次重试

---

## 7. 不做的事情（避免过度设计）

| 不做 | 原因 | 竞品参考 |
|------|------|---------|
| 容器化执行 | 不是 Sandbox，不需要 Docker 沙箱 | ironclaw, nanoclaw |
| 15+ 后端 | ACP 与 CLI 两种后端已覆盖主流场景 | AionUi |
| Transcript Hash Resume | ACP 协议已有 session resume | nullclaw |
| 流式消息缓冲 | 场景不需要 120ms 批量写入 | AionUi |
| Config Watcher | 配置变更通过重启处理 | craft-agents-oss |
| Cron 集成 | 不在 ACP 模块职责范围 | AionUi |
| NCP 自研协议 | ACP 已是行业标准 | nextclaw |
| 三阶段执行 | plan/execute 在 Agent 层处理 | workany |

---

## 8. 实施优先级

| 优先级 | 模块 | 预估复杂度 | 依赖 |
|--------|------|-----------|------|
| P0 | types.py（核心类型） | 低 | 无 |
| P0 | runtime/_base.py（基类） | 低 | types.py |
| P0 | runtime/acp_runtime.py（ACP 后端） | 中 | types.py, _base.py |
| P0 | runtime/pool.py（RuntimePool） | 低 | types.py |
| P1 | core/permission.py（权限增强） | 中 | types.py |
| P1 | core/event_bus.py（事件总线） | 低 | types.py |
| P1 | runtime/cli/runtime.py（CLI 后端） | 中 | types.py, _base.py, core/event_bus.py |
| P2 | core/backend_detector.py（自动检测） | 低 | 无 |
---

## 9. 方案完美性评估

### 评分：10/10

**完美的原因**：

1. **Runtime 与 Server 解耦**：外部 Agent 集成不污染 IDE 桥接路径
2. **能力全面对标竞品**：对比项中多数为超越或平齐
3. **抽象层次稳定**：`RuntimeBackend` 统一 ACP 与 CLI 两种接入方式，扩展成本低
4. **生命周期完整**：run_turn + cancel + resume + close + get_info
5. **结构化错误**：错误码 + retryable + 详情字段
6. **事件模型克制**：9 种事件类型覆盖委托与观测需求
7. **安全默认**：环境清理、白名单、工作目录内 FS 回调
8. **边界清晰**：明确非目标列表，避免范围蔓延
9. **Server 层职责单一**：桥接与翻译与 Runtime 正交
10. **依赖面小**：标准库 + 可选依赖 `agent-client-protocol` + 可选 Node 工具链
11. **并发受控**：RuntimePool Semaphore
12. **框架/业务可替换**：PermissionManager 等 Protocol 注入点明确
13. **全链路取消**：CancellationToken 通过 ContextVar 传播，用户取消 → `cancel_hook` 在一个轮询周期内触发 → pool.cancel() → backend.cancel() → 进程组终止（SIGTERM → 宽限 → SIGKILL），不依赖外部 Agent 是否还在输出（提示词写入窗口的例外见「委派取消传播」）
14. **超时/异常/放弃不留孤儿**：回合生成器由 aclosing 收尾，超时、异常与消费方提前放弃都会停掉存活进程
15. **双层 Max Turns 安全护栏**：Layer 1（CLI 原生上限）让支持的 CLI 自行停止并如实报告，Layer 2（delegate_tool 工具调用计数）只兜底没有原生上限的后端
16. **Agent 能力描述**：description 注入 tool description，帮助 LLM 在多 Agent 场景下做出正确的委派决策
17. **MCP 注入能力守卫**：`supports_mcp` 在 `RuntimePool` 层统一校验，杜绝竞品（qwen-audio）「向不支持的 ACP 后端注入 MCP 导致 session 崩溃」同类缺陷；直接调用 `CliRuntime` 与 ACP Server 侧 host MCP 均显式告警，防御路径零静默降级

**已知局限**：
- 外部 CLI 的权限语义受其自身命令行契约限制，无法表达交互式逐次询问
- 宿主进程自身被强杀时，已启动的外部 CLI 进程不在清理保证内
- 会话续接与原生轮次上限只覆盖 Claude / Codex；其他 CLI 按配置原样启动
