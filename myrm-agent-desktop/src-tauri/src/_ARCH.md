# Tauri Rust 后端

[INPUT]
- sidecar 二进制（POS: Python Backend + Agent Runner，release 打包产物）
- myrm-agent-frontend standalone（POS: Next 静态资源 bundle）
- Tauri 插件链（shell / updater / global-shortcut 等）

[OUTPUT]
- Tauri IPC 命令面、Sidecar 生命周期、系统 API 封装

[POS]
src-tauri/src/ Rust 源码根。入口 main.rs → app::run()。

---

## 架构概览

Tauri 桌面应用的 Rust 后端核心，负责：
1. **Python Sidecar** 进程管理（FastAPI API 服务器，监听 `api_port`）
2. **Next.js Sidecar** 进程管理（Standalone Server 前端服务器，监听 `webui_port`）
3. **Agent Sidecar** 进程管理（Bun 编译的独立二进制，CLI 工具集成）
4. **配置管理**（`SystemConfig`，包括 WebUI 模式、全局快捷键、最小化托盘配置等）
5. **系统 API 封装**（后台托盘动态状态、任务栏进度条、完成弹跳通知、系统级原生通知、文件对话框等）
6. **热键管理**（全局快捷键的动态 IPC 注册与拦截，含 Appshot 截屏快捷键、Voice PTT 语音对讲快捷键）
7. **端口冲突检测**（启动前检查端口占用，防止冲突）
8. **自动更新**（`tauri-plugin-updater`，前端通过 `@tauri-apps/plugin-updater` JS API 驱动）+ 启动期 Updater pubkey 占位符强校验（`utils/updater_safety.rs`，防止生产构建在未配置真实 pubkey 时启用 OTA，规避供应链攻击风险）

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `main.rs` | ✅ 核心 | 二进制入口，委托 `app/` | ✅ |
| `app/` | ✅ 核心 | Tauri Builder、插件、setup、快捷键、托盘、优雅停机 | — |
| `runtime/` | ✅ 核心 | Sidecar 运行时（见下表） | ✅ |
| `runtime/python_backend.rs` | ✅ 核心 | Python 后端 Sidecar 启动/停止/健康检查 IPC；dev 用 venv，release 校验 sidecar 非空；冷启动最多 30s `/health` 轮询 | ✅ |
| `runtime/watchdog.rs` | ✅ 核心 | 后端 Sidecar 健康监控与崩溃自动恢复（30s 周期检查、指数退避重启、循环崩溃保护） | ✅ |
| `runtime/nextjs_frontend.rs` | ✅ 核心 | Next.js Standalone 前端进程（Tauri 启动时始终自启） | ✅ |
| `runtime/appshot/` | ✅ 核心 | 全局快捷键：Appshot 截屏、Voice PTT、窗口 toggle（见 `runtime/appshot/_ARCH.md`） | ✅ |
| `runtime/setup_token.rs` | ✅ 核心 | WebUI Remote Setup Token 状态与 IPC | ✅ |
| `runtime/agent_runner.rs` | ✅ 核心 | Agent Runner 路径解析、启动与事件转发 | ✅ |
| `runtime/port.rs` | ✅ 工具 | 端口占用检测 | ✅ |
| `config.rs` | ✅ 核心 | 配置管理（`SystemConfig`, `BackendConfig`, `FrontendConfig`），端口管理，含 `appshot_shortcut`、`voice_ptt_shortcut` 和 `appshot_excluded_apps` 隐私黑名单字段 | ✅ |
| `commands/` | ✅ 核心 | Tauri IPC 命令（config、agent、overlay、recovery）→ 叶子清单见 [commands/_ARCH.md](commands/_ARCH.md) | — |
| `utils/` | ✅ 工具 | 系统工具封装 → 见 [utils/_ARCH.md](utils/_ARCH.md) | — |
---

## 子模块

| 模块 | 路径 | 职责 | 文档 |
|------|------|------|------|
| **app** | `./app/` | Tauri Builder、setup、快捷键、托盘、优雅停机 | [app/_ARCH.md](app/_ARCH.md) |
| **cli_agent_types** | `./cli_agent_types.rs` | CLI 可视化共享类型 | — |
| **runtime** | `./runtime/` | Sidecar 编排、Appshot、Setup Token | [runtime/_ARCH.md](runtime/_ARCH.md) |
| **agent_runner_rpc** | `./agent_runner_rpc/` | Agent Runner JSON-RPC 进程管理 | [agent_runner_rpc/_ARCH.md](agent_runner_rpc/_ARCH.md) |
| **sessions** | `./sessions/` | CLI 会话生命周期 | [sessions/_ARCH.md](sessions/_ARCH.md) |
| **permissions** | `./permissions/` | Explore/Ask/Auto 权限 | [permissions/_ARCH.md](permissions/_ARCH.md) |
| **commands** | `./commands/` | Tauri IPC 命令（含 `agent/` 子模块） | [commands/_ARCH.md](commands/_ARCH.md) · [commands/agent/_ARCH.md](commands/agent/_ARCH.md) |
| **utils** | `./utils/` | 平台系统工具 | [utils/_ARCH.md](utils/_ARCH.md) |

---

## 依赖关系

### 内部依赖
- `commands/agent/` → `agent_runner_rpc/`：CLI IPC 仅经 Agent Runner 进程
- `commands/` → `cli_agent_types/`, `sessions/`, `config/`：IPC 命令与会话、配置

### 外部依赖
- `tauri`：桌面应用框架
- `tauri-plugin-shell`：进程管理
- `tauri-plugin-dialog`：系统对话框
- `tauri-plugin-updater`：自动更新（检查/下载/安装，前端 JS API 驱动）
- `tauri-plugin-window-state`：窗口位置/尺寸跨重启持久化（三平台）
- `tokio`：异步运行时
- `serde`：序列化/反序列化
- `base64`：Appshot 截图 Base64 编码

---

## 三进程架构

```
Tauri 主进程 (Rust)
    ├─→ Python Backend Sidecar (FastAPI, Desktop :8080 / WebUI :api_port)
    │   └── API 端点：/api/v1/*
    │
    ├─→ Next.js Frontend Sidecar (Standalone Server, :webui_port，始终自启)
    │   ├── 提供静态前端资源
    │   └── 反向代理：/api/v1/* → http://localhost:{backend.port}/api/v1/*
    │
    └─→ Agent Runner Sidecar (standalone binary, JSON-RPC)
        └── CLI 工具集成（Claude Code, Codex, Gemini）
```

Release 模式 WebView 先加载 `frontend-shell/`（`withGlobalTauri: true`），IPC 读取 `webui_port` 后轮询 Next 就绪并跳转。

---

## 系统配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_webui_mode` | `bool` | `false` | WebUI 服务器模式：切换 Python 后端端口/绑定（Desktop 8080 vs WebUI 25808）；**不**控制 Next 自启 |
| `enable_remote_access` | `bool` | `false` | 允许远程访问（`0.0.0.0` vs `127.0.0.1`），同时生成 Setup Token |
| `webui_port` | `u16` | `3000` | Next.js 前端服务器监听端口 |
| `api_port` | `u16` | `25808` | WebUI 模式下 Python FastAPI 端口（Desktop 模式 Backend 固定 8080，忽略此字段） |

当 `enable_remote_access=true` 时，Rust 端生成 UUID setup token：
- 通过 `WEBUI_SETUP_TOKEN` 环境变量传给 Python 后端
- 存入 `SetupTokenState`，前端 WebView 通过 `get_setup_token` IPC 命令查询
- 用于首次 admin 账户创建的安全验证

---

## 消息类型（Agent Runner → 前端，JSON 事件）

| 类型 | 说明 | 通道 |
|-----|------|------|
| `text` | 文本内容 | `agent:message:{session_id}` |
| `thought` | 思考过程 | 同上 |
| `tool_call_start` | 工具调用开始 | 同上 |
| `tool_call_result` | 工具调用结果 | 同上 |
| `permission_request` | 权限请求 | `agent:permission:{session_id}` |
| `session_status` | 会话状态 | `agent:status:{session_id}` |
