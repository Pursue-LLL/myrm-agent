# platform_utils 模块架构


---

## 架构概述

平台适配层。通过协议接口抽象 Sandbox 和本地模式的差异，实现运行时自动切换。

**核心原则**：`myrm-agent-server` 在用户专属云电脑内以单用户实例运行（容器或 microVM 由供给后端决定）。Sandbox 模式下 CP **在基础设施层**调度云电脑并注入 env；`platform_utils/sandbox/` 通过 HTTP 调用 CP internal API（entitlements/budget）。**CP 不对用户暴露**；AgentScope/QwenPaw 等托管云端同样在后台编排实例，差异见 `myrm-control-plane/ARCHITECTURE.md`「术语澄清」。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | 平台服务入口：数据库/存储/文件服务/执行策略单例；导出 `get_deployment_capabilities` | ✅ |
| `deployment_capabilities.py` | ✅ 核心 | 启动时构建语义能力位（local/tauri/sandbox/remote） | ✅ |
| `execution.py` | ✅ 核心 | Agent 执行策略抽象（ExecutionStrategy Protocol + LocalExecutionStrategy） | 永远返回本地执行策略 |
| `workspace_root.py` | ✅ 辅助 | 工作区根路径解析（`get_workspace_root`：当前运行绑定的根，运行之外取进程工作目录；为某个会话服务的代码改用 `resolve_chat_workspace_root`） | ✅ |
| `workspace_session.py` | ✅ 辅助 | chat_id → `chat_{id}` workspace session SSOT（Goal progress hydrate） | ✅ |

---

## 子模块

| 模块 | 职责 |
|------|------|
| `sandbox/` | Sandbox 模式实现（控制平面配额与预算、tool gateway、SaaS 首启种子） |

---

## 关键功能

### LangGraph Checkpointer（创建与注入）

**创建**由框架包 `myrm_agent_harness.runtime.checkpointing.factory.create_checkpointer()` 完成（按 `settings.database.checkpointer_mode`、`sqlite_db_path`、`deploy_mode` 等参数）。

**启动注入**：`app/server/lifespan.py` 在 `_phase_1b_parallel()` → `_init_checkpointer_task()` 中 `await create_checkpointer(...)`，随后调用 `app.platform_utils.set_checkpointer(checkpointer)` 写入全局单例。

**读取**：业务与路由通过 `app.platform_utils.get_checkpointer()` 获取；若启动未完成初始化则 **raise RuntimeError**（禁止 silent MemorySaver fallback）。

**`create_checkpointer()` 返回 `(checkpointer, cleanup_callback)`**：清理回调由 lifespan 持有，在应用关闭阶段释放底层连接等资源；具体分支（memory/sqlite）以 harness 内实现为准。

#### 存储层结构（概念）

```
LangGraph 官方 Saver (AsyncSqliteSaver)
  ├─ 对话状态持久化（checkpoints 表）
  └─ 由 LangGraph 框架自动调用（每步自动保存/恢复）

装饰器: LoadFallbackCheckpointer（harness `runtime/checkpointing/load_fallback.py`）
  ├─ 转发 saver 的全部异步接口（含 adelete_thread）
  └─ 无法反序列化的旧 checkpoint 读作"无 checkpoint"（开启全新会话，不使每轮失败）
```

#### 生命周期管理

- **启动**：`app/server/lifespan.py::optimized_lifespan` 调度 `_init_checkpointer_task()` → `create_checkpointer()` → `set_checkpointer()`
- **关闭**：调用 harness 返回的 cleanup 回调清理连接资源
- **清理**：业务层通过 `cp.adelete_thread(thread_id)` 清除已删除会话的 checkpoint 数据；truncate/rewind 通过 `session_continuity_service.invalidate_chat_checkpoint` 对齐 DB 与 checkpoint。调用点：永久删除 / 清空回收站 / 两个自动清除 / 安全清空 / 焦点刷新（均经 `services/chat/chat_disposal.clear_conversation_state`）、fork 回滚、Resume 失败恢复
- **错误处理**：sqlite 模式 `create_checkpointer()` fail-fast（启动失败）；`get_checkpointer()` 未注入时 **RuntimeError**
- **恢复容错**：如果历史 checkpoint 因序列化类签名变更等原因无法反序列化，增量 checkpointer 会记录警告并按“无历史状态”重新启动，避免单条坏数据阻断整个流式请求

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHECKPOINTER_MODE` | (空) | 强制指定模式：`memory`/`sqlite`（空 = sqlite） |
| `DEPLOY_MODE` | `local` | 部署模式：`local`/`tauri`/`sandbox` |
| `MYRM_ALLOW_LOCAL_SKILLS` | (空/自动) | 显式控制本地技能持久化权限：`0`/`1`（默认 local 与 sandbox 自动允许） |
| `MYRM_DATA_DIR` | `~/.myrm` | 数据根目录；`data.db` / `checkpoints.db` / `qdrant` / `.estop_state.json` 等由此派生 |
| `DATABASE_URL` | (无) | 可选：PostgreSQL + AGE 图存储（默认 SQLite 图存储） |

---

## 部署方式总览

`myrm-agent-server` 支持两种部署模式，由 `DEPLOY_MODE` 环境变量控制：

### Local（本地模式：桌面客户端 / 本地 WebUI）

- **运行方式**：Tauri Sidecar 启动、`uv run run.py` 或 `python -m app.main`
- **数据库**：SQLite（嵌入式）
- **向量库**：Qdrant embedded
- **认证**：本机回环访问，或通过 `SANDBOX_API_KEY` 进行单租户访问
- **Agent 执行**：本地进程
- **前端**：Tauri WebView / `bun run dev`（开发）/ `bun run build && bun run start`（生产）
- **Docker 全栈部署**：`uv run deploy.py docker` 或 `docker compose --profile app up -d`
  - 后端 + 前端一键启动（SQLite，无外部数据库依赖）
  - 访问 http://localhost:3000（前端）/ http://localhost:25808（后端 API）

### Sandbox（云端，Agent-in-Sandbox）

- **运行方式**：`myrm-agent-server` 打包为镜像，由控制平面调度到用户专属云电脑
- **架构**：`myrm-agent-server` 运行在 per-user 云电脑内（harness、浏览器、终端、文件系统、代码执行同机），控制平面是独立服务
- **数据库**：SQLite（`settings.database.sqlite_path`，默认 `{MYRM_DATA_DIR}/data.db`）
- **向量库**：Qdrant embedded（`settings.database.qdrant_path`，默认 `{MYRM_DATA_DIR}/qdrant`）
- **认证**：通过 `SANDBOX_API_KEY` 进行单租户访问
- **Agent 执行**：云电脑内本地进程
- **安全**：由供给后端提供（Docker+gVisor 的 seccomp/AppArmor，或 Firecracker microVM 的内核级隔离）
- **持久化**：per-user 持久化卷，Sleep 前自动备份

---

## Agent-in-Sandbox 架构（Sandbox 模式）

### 架构原则

`myrm-agent-server` 是运行在云电脑**内部**的业务执行体。控制服务是**独立部署的外部组件**，负责云电脑生命周期管理。两者完全解耦：

- `myrm-agent-server` 不依赖、不导入、不感知控制平面的存在
- 控制平面通过环境变量向 `myrm-agent-server` 注入配置（`DEPLOY_MODE`、`MYRM_DATA_DIR` 或 CP 卷挂载路径等）
- 云电脑分配策略为 per-user（每用户一台持久化云电脑）

```
[外部] 控制服务（独立部署）
  ├── 用户认证、任务队列、计费
  ├── 云电脑生命周期管理（create/sleep/wake/destroy）
  └── 为每个用户创建独立云电脑（per-user）
        ↓ 注入配置（env vars: DEPLOY_MODE=sandbox, MYRM_DATA_DIR, ...)
[云电脑内] myrm-agent-server (per-user, DEPLOY_MODE=sandbox)
  ├── GeneralAgent → 本地执行（LocalExecutionStrategy）
  ├── myrm-agent-harness → 框架层工具包
  └── 不感知控制平面的存在
```

### 独立部署能力

`myrm-agent-server` 在所有模式下均可独立运行：

| 模式 | 外部依赖 | 启动命令 |
|------|---------|---------|
| Local | 无 | Tauri Sidecar / `DEPLOY_MODE=local uv run run.py` |
| Local Docker | 无 | `docker compose --profile app up -d` |
| Sandbox | 控制平面（管理云电脑生命周期 + 持久化卷） | 由控制平面创建云电脑并注入配置 |

### Sandbox 部署流程

Sandbox 部署由两个独立部分组成：

**1. 构建运行时镜像**（`myrm-agent-server` + `myrm-agent-harness` 打包）：

```bash
docker build -f myrm-agent/myrm-agent-server/docker/Dockerfile.official -t myrm/runtime:latest .
# 生成 myrm/runtime:latest 镜像（CP 契约 DEFAULT_AGENT_SERVER_IMAGE 默认引用）
```

**2. 部署控制服务**（与 agent 镜像分开发布）：

控制服务负责：
- 管理用户认证和任务队列
- 为每个用户创建 `myrm-runtime` 云电脑实例（镜像由 CP 契约 `DEFAULT_AGENT_SERVER_IMAGE` 指定；容器 / microVM 由供给后端决定）+ per-user 持久化卷
- 注入环境变量（`DEPLOY_MODE=sandbox`、`MYRM_DATA_DIR` 等）
- 管理沙箱生命周期（sleep/wake/destroy）
- Sleep 前自动备份持久化卷

控制服务的部署与版本发布由运维侧单独维护（不在本仓库）。

### 控制平面与 myrm-agent-server 的通信方式

`myrm-agent-server` 的核心业务请求链仍以“环境变量注入 + HTTP 反向代理”为主，不要求业务层自己维护一个强耦合的控制平面客户端；但在当前 `sandbox` 架构下，系统存在上行遥测与下次唤醒上报两个适配器，因此此处应按真实代码拆分理解：

| 通信方向 | 方式 | 说明 |
|---------|------|------|
| 控制平面 → myrm-agent-server | 环境变量注入（创建时一次性） | 创建云电脑时注入 `DEPLOY_MODE`、`MYRM_DATA_DIR` 等配置 |
| 用户 → agent-server | HTTP/WS（`/proxy/me/*` 或 `/proxy/{sandbox_id}/*`） | CP 反向代理 + HMAC 验签头注入；SaaS 前端 `NEXT_PUBLIC_API_BASE_URL=https://<cp>/proxy/me/api/v1` |
| 控制平面 → 云电脑 | Docker / Fly / E2B API（按后端） | 云电脑生命周期管理（pause/stop/rm），`myrm-agent-server` 业务逻辑本身不参与 |
| myrm-agent-server / 云电脑 → 控制平面 | stdout 日志采集 + 可选 HTTP 遥测上报 + 下次唤醒时刻上报 | 结构化日志被动采集；少量 `sandbox` 专属指标可通过显式适配器上报控制平面；`services/sandbox_wake` 把 goal/cron/看板的下一次必须运行时间 `PUT` 给 CP（`/api/internal/sandboxes/{id}/wake-schedule`），CP 到点唤醒已暂停的云电脑 |

**per-user 模型下的通信流程**（当前真实实现）：

```
1. 控制平面为用户创建云电脑（注入 env vars）
2. 用户浏览器 → CP `/proxy/me/*`（JWT）→ HMAC 签名 → agent-server:25808/api/v1/...
3. myrm-agent-server 作为 HTTP 服务持续运行，接收多次用户请求
4. 空闲且无在途工作时被控制平面暂停/休眠（Docker pause；Fly 停机器）；goal/cron/看板顺延到未来时，云电脑上报下次唤醒时刻，CP 到点唤醒，用户回来时同样唤醒
```

**为什么是 per-user 云电脑**：

| 模型 | 分配粒度 | 生命周期 | 通信模式 |
|------|---------|---------|---------|
| 临时任务沙箱 | 每个任务一个沙箱 | 任务结束回收 | 一次性注入，沙箱内自循环 |
| **MyrmAgent（per-user 云电脑）** | 每个用户一台 | 长期持久，空闲休眠 / 唤醒 | HTTP 主通道 + 遥测 / 下次唤醒上报（HTTP） |

结论上应区分两层含义：

1. `myrm-agent-server` 的核心业务处理仍然不依赖一个强耦合的控制平面 SDK 或 RPC 协议。
2. 但当前 `sandbox` 体系已经真实存在显式遥测与下次唤醒上报适配器（均为 HTTP，无 WebSocket 辅助通道），因此文档不应再描述为“完全无控制平面通信”。

### 控制平面职责边界

| 职责 | 归属 | 说明 |
|------|------|------|
| 用户认证、计费 | 控制平面 | 管理多租户 |
| 任务队列、调度 | 控制平面 | 接收用户请求并分派到云电脑 |
| 云电脑创建/销毁 | 控制平面 | 容器 / microVM 生命周期管理（按供给后端） |
| 请求路由 | 控制平面 | 反向代理，将用户请求转发到对应云电脑 |
| 日志采集 | 控制平面 | 被动采集 myrm-agent-server stdout 日志 |
| Agent 执行逻辑 | myrm-agent-server（云电脑内） | 本地进程执行，不感知外部 |
| 数据库、认证选择 | myrm-agent-server 的 platform_utils 层 | 根据 DEPLOY_MODE 自动适配 |
| 框架层工具包 | myrm-agent-harness | 浏览器、代码执行、搜索等 |

---

## ExecutionStrategy（Agent 执行策略）

`execution.py` 定义 `ExecutionStrategy` Protocol 和 `LocalExecutionStrategy`。

服务器永远使用 `LocalExecutionStrategy`，因为无论部署在何处（本地、云电脑内），Agent 都在当前进程内执行。

---

## 依赖关系

- `app/config/`：部署模式判断 (`DEPLOY_MODE`)
- `langgraph.checkpoint.*`：checkpointer 实现（框架层提供）
- **不依赖**外部控制服务（单机/local 模式可独立运行；sandbox 模式由控制服务托管云电脑）
