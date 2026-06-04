# Tauri Rust 后端


---

## 架构概览

Tauri 桌面应用的 Rust 后端核心，负责：
1. **Python Sidecar** 进程管理（FastAPI API 服务器，监听 `api_port`）
2. **Next.js Sidecar** 进程管理（Standalone Server 前端服务器，监听 `webui_port`）
3. **Agent Sidecar** 进程管理（Bun 编译的独立二进制，CLI 工具集成）
4. **配置管理**（`SystemConfig`，包括 WebUI 模式、全局快捷键、最小化托盘配置等）
5. **系统 API 封装**（后台托盘动态状态、任务栏进度条、完成弹跳通知、系统级原生通知、文件对话框等）
6. **热键管理**（全局快捷键的动态 IPC 注册与拦截，含 Appshot 截屏快捷键）
7. **端口冲突检测**（启动前检查端口占用，防止冲突）
8. **自动更新**（`tauri-plugin-updater`，前端通过 `@tauri-apps/plugin-updater` JS API 驱动）+ 启动期 Updater pubkey 占位符强校验（`utils/updater_safety.rs`，防止生产构建在未配置真实 pubkey 时启用 OTA，规避供应链攻击风险）

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `main.rs` | ✅ 核心 | Tauri 应用入口：插件注册、setup、invoke_handler、Agent Sidecar 事件转发 | ✅ |
| `runtime/` | ✅ 核心 | Sidecar 运行时（见下表） | ✅ |
| `runtime/python_backend.rs` | ✅ 核心 | Python 后端 Sidecar 启动/停止/健康检查 IPC | ✅ |
| `runtime/nextjs_frontend.rs` | ✅ 核心 | Next.js Standalone 前端进程（WebUI 模式） | ✅ |
| `runtime/appshot.rs` | ✅ 核心 | Appshot 全局快捷键截屏与窗口文本提取 | ✅ |
| `runtime/setup_token.rs` | ✅ 核心 | WebUI Remote Setup Token 状态与 IPC | ✅ |
| `runtime/agent_runner.rs` | ✅ 核心 | Agent Runner 路径解析、启动与事件转发 | ✅ |
| `runtime/port.rs` | ✅ 工具 | 端口占用检测 | ✅ |
| `config.rs` | ✅ 核心 | 配置管理（`SystemConfig`, `BackendConfig`, `FrontendConfig`），端口管理，含 `appshot_shortcut` 字段 | ✅ |
| `lifecycle.rs` | ✅ 核心 | 优雅停机与生命周期管理 | ✅ |
| `tray.rs` | ✅ 核心 | 系统托盘初始化（Show/New Chat/Settings/Workspace/Quit 菜单 + 左键显示窗口）与 tooltip 状态管理。前端 `useTrayStatus` hook 还通过 Tauri JS API 控制任务栏进度条（`setProgressBar`）和完成弹跳通知（`requestUserAttention`） | ✅ |
| `commands/` | ✅ 核心 | Tauri IPC 命令模块（config, agent） | ✅ |
| `utils/` | ✅ 工具 | 系统工具封装（`quarantine.rs` 隔离检测, `auth.rs` 原生提权, `power.rs` 智能电源锁防休眠[跨平台RAII, macOS 使用 IOKit 原生 API], `screen_lock.rs` 屏幕锁定管理[检测/解锁/重锁/Keychain], `updater_safety.rs` 启动期 Tauri Updater pubkey 占位符强校验） | ✅ |
| `commands/visual_approval_overlay.rs` | ✅ 核心 | Tauri OS 视觉审批红框 overlay IPC（screen/image 坐标模式 + 显示器门控） | ✅ |
| `commands/power.rs` | ✅ 核心 | 电源管理 IPC 命令（`power_lock_acquire`/`release`/`status`），支持 `prevent_display_sleep` 参数控制显示器保持唤醒 | ✅ |
| `commands/screen_lock.rs` | ✅ 核心 | 屏幕锁定管理 IPC 命令（`screen_is_locked`/`screen_unlock`/`screen_relock`/`screen_lock_store_password`/`screen_lock_has_password`/`screen_lock_delete_password`/`screen_lock_platform_support`） | ✅ |
| `tunnel.rs` | ✅ 辅助 | 解析 bundled cloudflared 路径；停机时调用 Server `/tunnel/stop` | ✅ |

---

## 子模块

| 模块 | 路径 | 职责 | 文档 |
|------|------|------|------|
| **agents** | `./agents/` | CLI Agent 适配器（Claude Code、Codex、Gemini） | ✅ |
| **runtime** | `./runtime/` | Python/Next.js Sidecar、Appshot、Setup Token、Agent Runner 编排 | ✅ |
| **sidecar** | `./sidecar/` | Agent Runner Sidecar 进程管理（Bun compile 二进制） | ✅ |
| **sessions** | `./sessions/` | CLI 会话生命周期管理 | ✅ |
| **permissions** | `./permissions/` | 权限管理（Explore/Ask/Auto） | ✅ |
| **commands** | `./commands/` | Tauri IPC 命令实现（Agent + Config） | ✅ |
| **utils** | `./utils/` | 系统工具（macOS 隔离修复、原生提权、智能电源锁防休眠、屏幕锁定管理、Updater pubkey 安全校验） | ✅ |

---

## 依赖关系

### 内部依赖
- `agents/` → `sidecar/`：Agent 适配器依赖 Sidecar 进程管理
- `commands/` → `agents/`, `sessions/`, `config/`：IPC 命令调用 Agent、会话管理和配置

### 外部依赖
- `tauri`：桌面应用框架
- `tauri-plugin-shell`：进程管理
- `tauri-plugin-dialog`：系统对话框
- `tauri-plugin-updater`：自动更新（检查/下载/安装，前端 JS API 驱动）
- `tokio`：异步运行时
- `serde`：序列化/反序列化
- `base64`：Appshot 截图 Base64 编码

---

## 三进程架构（WebUI 模式）

```
Tauri 主进程 (Rust)
    ├─→ Python Backend Sidecar (FastAPI, :api_port)
    │   └── API 端点：/api/v1/*
    │
    ├─→ Next.js Frontend Sidecar (Standalone Server, :webui_port)
    │   ├── 提供静态前端资源
    │   └── 反向代理：/api/v1/* → http://localhost:api_port/api/v1/*
    │
    └─→ Agent Runner Sidecar (standalone binary, JSON-RPC)
        └── CLI 工具集成（Claude Code, Codex, Gemini）
```

---

## WebUI 模式配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_webui_mode` | `bool` | `false` | 启用 WebUI 服务器模式 |
| `enable_remote_access` | `bool` | `false` | 允许远程访问（`0.0.0.0` vs `127.0.0.1`），同时生成 Setup Token |
| `webui_port` | `u16` | `3000` | Next.js 前端服务器监听端口 |
| `api_port` | `u16` | `25808` | Python FastAPI 监听端口 |

当 `enable_remote_access=true` 时，Rust 端生成 UUID setup token：
- 通过 `WEBUI_SETUP_TOKEN` 环境变量传给 Python 后端
- 存入 `SetupTokenState`，前端 WebView 通过 `get_setup_token` IPC 命令查询
- 用于首次 admin 账户创建的安全验证

---

## 消息类型（agents → 前端）

| 类型 | 说明 | Rust 类型 |
|-----|------|----------|
| `text` | 文本内容 | `AgentMessage::Text` |
| `thought` | 思考过程 | `AgentMessage::Thought` |
| `tool_call_start` | 工具调用开始 | `AgentMessage::ToolCallStart` |
| `tool_call_result` | 工具调用结果 | `AgentMessage::ToolCallResult` |
| `permission_request` | 权限请求 | `AgentMessage::PermissionRequest` |
| `session_status` | 会话状态 | `AgentMessage::SessionStatus` |
