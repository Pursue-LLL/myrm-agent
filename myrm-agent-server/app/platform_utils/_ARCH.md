# platform_utils 模块架构


---

## 架构概述

平台适配层。通过协议接口抽象 Sandbox 和本地模式的差异，实现运行时自动切换。

**核心原则**：`myrm-agent-server` 在容器内以单用户实例运行。Sandbox 模式下 CP 负责调度与 env 注入；`platform_utils/sandbox/` 通过 HTTP 调用 CP internal API（entitlements/budget）。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | 平台服务入口：数据库/存储/文件服务/执行策略单例；导出 `get_deployment_capabilities` | ✅ |
| `deployment_capabilities.py` | ✅ 核心 | 启动时构建语义能力位（local/tauri/sandbox/remote） | ✅ |
| `execution.py` | ✅ 核心 | Agent 执行策略抽象（ExecutionStrategy Protocol + LocalExecutionStrategy） | 永远返回本地执行策略 |
| `protocols.py` | ✅ 核心 | 平台协议接口定义（FileService, ExecutionStrategy 等） |
| `workspace_root.py` | ✅ 辅助 | 工作区根路径解析（`get_workspace_root`，供 core/services/api 共用） | ✅ |

---

## 子模块

| 模块 | 职责 |
|------|------|
| `sandbox/` | Sandbox 模式实现（云端存储等） |
| `local/` | 本地模式实现（本地文件服务等） |

---

## 关键功能

### LangGraph Checkpointer（创建与注入）

**创建**由框架包 `myrm_agent_harness.runtime.checkpointing.factory.create_checkpointer()` 完成（按 `settings.database.checkpointer_mode`、`sqlite_db_path`、`database_url`、`deploy_mode` 等参数）。

**启动注入**：`app/server/lifespan.py` 在 `_phase_1b_parallel()` → `_init_checkpointer_task()` 中 `await create_checkpointer(...)`，随后调用 `app.platform_utils.set_checkpointer(checkpointer)` 写入全局单例。

**读取**：业务与路由通过 `app.platform_utils.get_checkpointer()` 获取；若启动未完成初始化，则 `__init__.py` 内懒加载 **MemorySaver** 作为兜底（并打日志提示应在启动路径注入）。

**`create_checkpointer()` 返回 `(checkpointer, cleanup_callback)`**：清理回调由 lifespan 持有，在应用关闭阶段释放底层连接等资源；具体分支（memory/sqlite/postgres）以 harness 内实现为准。

#### 存储层结构（概念）

```
LangGraph 官方 Saver (AsyncSqliteSaver/AsyncPostgresSaver)
  ├─ 对话状态持久化（checkpoints 表）
  └─ 由 LangGraph 框架自动调用（每步自动保存/恢复）

装饰器: IncrementalSessionCheckpointer
  ├─ 增量保存（hash 去重）
  ├─ 浏览器会话追踪（SessionVault）
  └─ 线程追踪（ThreadStore）

ThreadStore（线程生命周期管理）
  ├─ 任务注册（checkpoint_threads 表）
  ├─ 僵尸检测（48h 未活跃 → failed）
  └─ 自动恢复（应用重启后恢复活跃会话）
```

#### 生命周期管理

- **启动**：`app/server/lifespan.py::optimized_lifespan` 调度 `_init_checkpointer_task()` → `create_checkpointer()` → `set_checkpointer()`
- **关闭**：调用 harness 返回的 cleanup 回调清理连接资源
- **清理**：业务层通过 `cp.adelete_thread(thread_id)` 清除已删除会话的 checkpoint 数据，避免孤儿 checkpoint 持续占用存储。调用点：永久删除（`chat_crud._cleanup_checkpointer`）、清空回收站、焦点刷新、fork 回滚、Resume 失败恢复
- **错误处理**：以 harness / lifespan 实现为准；`get_checkpointer()` 惰性 fallback 仅用于健壮性
- **恢复容错**：如果历史 checkpoint 因序列化类签名变更等原因无法反序列化，增量 checkpointer 会记录警告并按“无历史状态”重新启动，避免单条坏数据阻断整个流式请求

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHECKPOINTER_MODE` | (空) | 强制指定模式：`memory`/`sqlite`/`postgres` |
| `DEPLOY_MODE` | `local` | 部署模式：`local`/`tauri`/`sandbox` |
| `MYRM_DATA_DIR` | `~/.myrm` | 数据根目录；`data.db` / `checkpoints.db` / `qdrant` 等由此派生 |
| `DATABASE_URL` | (无) | PostgreSQL 连接串（仅 `CHECKPOINTER_MODE=postgres` 时使用） |

---

## 部署方式总览

`myrm-agent-server` 支持两种部署模式，由 `DEPLOY_MODE` 环境变量控制：

### Local（本地模式：桌面客户端 / CLI WebUI）

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

- **运行方式**：`myrm-agent-server` 打包为 Docker 镜像，由外部控制服务管理
- **架构**：`claw-server` 运行在 per-user 沙箱容器内，控制平面是独立服务
- **数据库**：SQLite（`settings.database.sqlite_path`，默认 `{MYRM_DATA_DIR}/data.db`）
- **向量库**：Qdrant embedded（`settings.database.qdrant_path`，默认 `{MYRM_DATA_DIR}/qdrant`）
- **认证**：通过 `SANDBOX_API_KEY` 进行单租户访问
- **Agent 执行**：本地进程（沙箱内即本地）
- **安全**：gVisor (runsc) + seccomp + AppArmor（由容器运行时提供）
- **持久化**：per-sandbox Docker 卷（`myrm`），Sleep 前自动备份

---

## Agent-in-Sandbox 架构（Sandbox 模式）

### 架构原则

`myrm-agent-server` 是运行在沙箱容器**内部**的业务执行体。控制服务是**独立部署的外部组件**，负责沙箱生命周期管理。两者完全解耦：

- `claw-server` 不依赖、不导入、不感知控制平面的存在
- 控制平面通过环境变量向 `claw-server` 注入配置（`DEPLOY_MODE`、`MYRM_DATA_DIR` 或 CP 卷挂载路径等）
- 沙箱分配策略为 per-user（每用户一个持久化容器）

```
[外部] 控制服务（独立部署）
  ├── 用户认证、任务队列、计费
  ├── 沙箱生命周期管理（create/sleep/wake/destroy）
  └── 为每个用户创建独立容器（per-user）
        ↓ 注入配置（env vars: DEPLOY_MODE=sandbox, MYRM_DATA_DIR, ...)
[沙箱内] Docker Container (per-user)
  └── myrm-agent-server（DEPLOY_MODE=sandbox）
      ├── GeneralAgent → 本地执行（LocalExecutionStrategy）
      ├── myrm-agent-harness → 框架层工具包
      └── 不感知控制平面的存在
```

### 独立部署能力

`claw-server` 在所有模式下均可独立运行：

| 模式 | 外部依赖 | 启动命令 |
|------|---------|---------|
| Local | 无 | Tauri Sidecar / `DEPLOY_MODE=local uv run run.py` |
| Local Docker | 无 | `docker compose --profile app up -d` |
| Sandbox | 控制平面（管理沙箱生命周期 + 持久化卷） | 由控制平面创建容器并注入配置 |

### Sandbox 部署流程

Sandbox 部署由两个独立部分组成：

**1. 构建 Agent 沙箱镜像**（`claw-server` + `agent-harness` 打包）：

```bash
docker compose --profile sandbox build agent-image
# 生成 myrm-agent:latest 镜像
```

**2. 部署控制服务**（与 agent 镜像分开发布）：

控制服务负责：
- 管理用户认证和任务队列
- 为每个用户创建 `myrm-agent:latest` 容器 + per-user 持久化卷
- 注入环境变量（`DEPLOY_MODE=sandbox`、`MYRM_DATA_DIR` 等）
- 管理沙箱生命周期（sleep/wake/destroy）
- Sleep 前自动备份持久化卷

控制服务的部署与版本发布由运维侧单独维护（不在本仓库）。

### 控制平面与 claw-server 的通信方式

`claw-server` 的核心业务请求链仍以“环境变量注入 + HTTP 反向代理”为主，不要求业务层自己维护一个强耦合的控制平面客户端；但在当前 `sandbox` 架构下，系统已经存在辅助实时通道和上行遥测适配器，因此此处应按真实代码拆分理解：

| 通信方向 | 方式 | 说明 |
|---------|------|------|
| 控制平面 → claw-server | 环境变量注入（创建时一次性） | 创建沙箱时注入 `DEPLOY_MODE`、`MYRM_DATA_DIR` 等配置 |
| 用户 → agent-server | HTTP/WS（`/proxy/me/*` 或 `/proxy/{sandbox_id}/*`） | CP 反向代理 + HMAC 验签头注入；SaaS 前端 `NEXT_PUBLIC_API_BASE_URL=https://<cp>/proxy/me/api/v1` |
| 控制平面 ↔ 沙箱辅助运行时 | WebSocket 辅助通道 | `sandbox_runtime` / WebSocket Gateway 负责资源上报、heartbeat、控制命令、token request；这是 `sandbox` 专属基础设施，不属于业务语义层 |
| 控制平面 → 容器 | Docker/K8s API | 容器生命周期管理（pause/unpause/rm），`claw-server` 业务逻辑本身不参与 |
| claw-server / 沙箱 → 控制平面 | stdout 日志采集 + 可选 HTTP 遥测上报 | 结构化日志被动采集；少量 `sandbox` 专属指标可通过显式适配器上报控制平面 |

**per-user 模型下的通信流程**（当前真实实现）：

```
1. 控制平面为用户创建容器（注入 env vars）
2. 用户浏览器 → CP `/proxy/me/*`（JWT）→ HMAC 签名 → agent-server:25808/api/v1/...
3. claw-server 作为 HTTP 服务持续运行，接收多次用户请求
4. `sandbox_runtime` 通过 WebSocket 辅助通道向控制平面上报资源、接收控制命令和申请 one-time token
5. 空闲时被控制平面 pause（Docker pause），用户回来时 unpause
```

**与 Manus per-task 模型的区别**：

| 模型 | 沙箱分配 | 沙箱生命周期 | 通信模式 |
|------|---------|------------|---------|
| Manus (per-task) | 每个任务一个沙箱 | 启动注入任务 → 执行 → Sleep → 回收 | 一次性注入，沙箱内自循环 |
| Happycapy (per-user) | 每个用户一个持久沙箱 | 长期持久化，空闲时 pause | HTTP 服务持续运行，接收多次请求 |
| **MyrmAgent (per-user)** | 每个用户一个持久沙箱 | 同 Happycapy，兼容 Sleep + 专用卷 | HTTP 主通道 + `sandbox` 辅助 WebSocket / 遥测通道 |

结论上应区分两层含义：

1. `claw-server` 的核心业务处理仍然不依赖一个强耦合的控制平面 SDK 或 RPC 协议。
2. 但当前 `sandbox` 体系已经真实存在辅助 WebSocket 通道与显式遥测适配器，因此文档不应再描述为“完全无实时直连”。

### 控制平面职责边界

| 职责 | 归属 | 说明 |
|------|------|------|
| 用户认证、计费 | 控制平面 | 管理多租户 |
| 任务队列、调度 | 控制平面 | 接收用户请求并分派到沙箱 |
| 沙箱创建/销毁 | 控制平面 | 容器生命周期管理 |
| 请求路由 | 控制平面 | 反向代理，将用户请求转发到对应容器 |
| 日志采集 | 控制平面 | 被动采集 claw-server stdout 日志 |
| Agent 执行逻辑 | claw-server（沙箱内） | 本地进程执行，不感知外部 |
| 数据库、认证选择 | claw-server 的 platform_utils 层 | 根据 DEPLOY_MODE 自动适配 |
| 框架层工具包 | myrm-agent-harness | 浏览器、代码执行、搜索等 |

---

## ExecutionStrategy（Agent 执行策略）

`execution.py` 定义 `ExecutionStrategy` Protocol 和 `LocalExecutionStrategy`。

服务器永远使用 `LocalExecutionStrategy`，因为无论部署在何处（本地、Sandbox 沙箱内），Agent 都在当前进程内执行。

---

## 依赖关系

- `app/config/`：部署模式判断 (`DEPLOY_MODE`)
- `langgraph.checkpoint.*`：checkpointer 实现（框架层提供）
- **不依赖**外部控制服务（单机/local 模式可独立运行；sandbox 模式由控制服务托管容器）
