# MyrmAgent Desktop

> **许可**: **开源**仓库。Tauri 桌面客户端，内嵌 `myrm-agent-server` 后端 Sidecar。

Tauri 桌面客户端 - 隐私优先的 AI 搜索和研究助手

## 🏗️ 架构

### 整体架构

```
┌─────────────────────────────────────┐
│  Tauri Shell (Rust)                 │
│  ├─ WebView (Next.js 静态导出)      │
│  ├─ 系统 API (文件/通知/对话框)     │
│  ├─ Python Sidecar 进程管理         │
│  └─ Agent Sidecar 进程管理          │
└─────────────────────────────────────┘
         ↓ IPC/HTTP           ↓ JSON-RPC
┌───────────────────┐  ┌────────────────────┐
│  Python Sidecar   │  │  Agent Sidecar     │
│  (PyInstaller)    │  │  (Bun compiled)    │
│  └─ FastAPI 后端  │  │  └─ CLI 工具集成   │
└───────────────────┘  │      ├─ Claude Code │
                       │      ├─ Codex       │
                       │      └─ Gemini CLI  │
                       └────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  本地存储                            │
│  ├─ SQLite (关系数据 + 图查询)      │
│  ├─ Qdrant 嵌入式 (向量)            │
│  └─ 本地文件系统 (文档)             │
└─────────────────────────────────────┘
```

### CLI 可视化工具架构 (2026-01-26)

CLI 可视化工具将 Claude Code、Codex、Gemini CLI 等命令行 AI 工具的操作过程可视化。

**数据流**：
```
用户输入 → Tauri IPC → Rust 后端 → Agent Sidecar (standalone binary)
                                    ↓
                            CLI Tool (claude, codex, gemini)
                                    ↓
          前端 UI ← Message 类型 ← cliAgentAdapter ← 流式响应
```

**Rust 后端模块**：
- `src-tauri/src/runtime/` — Python/Next.js Sidecar、Appshot、Setup Token
- `src-tauri/src/agents/` — CLI 适配器（Claude Code、Codex、Gemini；Sidecar 备用）
- `src-tauri/src/sidecar/` — Agent Runner 进程与 JSON-RPC
- `src-tauri/src/sessions/` — CLI 会话生命周期
- `src-tauri/src/permissions/` — 权限管理

**前端组件**：
- `MessageBox/ProgressSteps/` - 工具调用进度可视化
- `MessageBox/ToolCallApproval.tsx` - 权限审批弹窗
- `AgentConfigPanel/CLIWorkingDirectory.tsx` - 工作路径选择

**消息类型**：
| 类型 | 说明 |
|-----|------|
| `text` | 文本内容 |
| `thought` | 思考过程 |
| `tool_call_start` | 工具调用开始 |
| `tool_call_result` | 工具调用结果 |
| `permission_request` | 权限请求 |

## 📋 前置要求

### 📦 下载预编译包（推荐）

我们提供了开箱即用的预编译包，无需任何配置即可运行：

1. 访问 [GitHub Releases](https://github.com/Pursue-LLL/myrm-agent/releases/latest) 页面，或前往官网 [myrmagent.ai/download](https://myrmagent.ai/download)。
2. 下载对应您操作系统的安装包（`.dmg`, `.exe`, `.deb` 等）。
3. 双击安装并启动即可。

---

### 源码编译前置要求（仅开发需要）

#### 必需
- **Rust**: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Tauri CLI**: `cargo install tauri-cli`
- **Bun**: >= 1.1 (前端构建 + agent-runner 编译)
- **Python**: >= 3.14

### 可选
- **PyInstaller**: `pip install pyinstaller` (用于打包 Python 后端)

> **注意**: 用户无需安装 Node.js。Agent Runner 通过 `bun build --compile` 编译为独立二进制，已内含运行时。

## 🚀 开发

### 1. 安装依赖

```bash
# 前端依赖
cd ../myrm-agent-frontend
bun install

# Python 后端依赖
cd ../myrm-agent-server
uv sync --all-extras
```

### 2. 开发模式

```bash
# 方式 1: 使用 Tauri CLI（推荐）
cd myrm-agent-desktop
cargo tauri dev

# 方式 2: 手动启动
# 终端 1: 启动前端
cd myrm-agent-frontend
bun run dev

# 终端 2: 启动后端
cd myrm-agent-server
cp env.tauri.template .env.tauri
python deploy.py tauri dev

# 终端 3: 启动 Tauri
cd myrm-agent-desktop
cargo tauri dev
```

## 📦 打包

### 1. 打包所有 Sidecars

```bash
cd myrm-agent-desktop/sidecar
python build.py
```

这将生成平台特定的可执行文件：

**Python 后端**：
- **macOS**: `myrmagent-backend-aarch64-apple-darwin`
- **Linux**: `myrmagent-backend-x86_64-unknown-linux-gnu`
- **Windows**: `myrmagent-backend-x86_64-pc-windows-msvc.exe`

**Agent Runner** (Bun 编译为独立二进制，无需 Node.js)：
- **macOS**: `agent-runner-aarch64-apple-darwin`
- **Linux**: `agent-runner-x86_64-unknown-linux-gnu`
- **Windows**: `agent-runner-x86_64-pc-windows-msvc.exe`

### 2. 构建前端

```bash
cd myrm-agent-frontend
bun run build:tauri
```

### 3. 打包 Tauri 应用

```bash
cd myrm-agent-desktop
cargo tauri build
```

输出位置：
- **macOS**: `src-tauri/target/release/bundle/dmg/`
- **Linux**: `src-tauri/target/release/bundle/appimage/`
- **Windows**: `src-tauri/target/release/bundle/msi/`

## 🔧 配置

### 环境变量

复制并编辑配置文件：
```bash
cp ../myrm-agent-server/env.tauri.template ../myrm-agent-server/.env.tauri
```

关键配置：
- `DEPLOY_MODE=local`
- `DATABASE_MODE=sqlite`
- `QDRANT_MODE=embedded`
- `EMBEDDING_MODE=local`

### Tauri 配置

编辑 `src-tauri/tauri.conf.json`：
- 应用名称、版本、标识符
- 窗口大小、图标
- Sidecar 路径

## 📁 目录结构

```
myrm-agent-desktop/
├── _ARCH.md                # 模块架构与 Sidecar 对照表
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── entitlements.plist
│   ├── build.rs
│   ├── src/
│   │   ├── main.rs         # Tauri 入口（插件注册、setup、invoke_handler）
│   │   ├── _ARCH.md        # Rust 模块清单
│   │   ├── runtime/        # Python/Next.js Sidecar、Appshot、Agent Runner 编排
│   │   ├── commands/       # IPC 命令（config、agent、power、screen_lock…）
│   │   ├── agents/         # CLI 适配器（Sidecar 不可用时的 Rust fallback）
│   │   ├── sidecar/        # Agent Runner 进程与 JSON-RPC
│   │   ├── sessions/       # CLI 会话生命周期
│   │   ├── permissions/
│   │   ├── utils/
│   │   ├── lifecycle.rs
│   │   ├── tray.rs
│   │   └── tunnel.rs
│   ├── icons/              # 桌面 bundle 图标（icon.png / .icns / .ico）
│   └── binaries/           # 构建产物（gitignore，由 sidecar/build.py 生成）
├── sidecar/
│   ├── build.py            # Python 后端 + agent-runner 打包
│   ├── agent-runner/       # Agent Runner TypeScript 源码（Bun）
│   └── README.md
├── scripts/
│   ├── download-cloudflared.sh
│   ├── verify-signing.sh
│   └── verify-signing.ps1
└── SIGNING.md
```

## 🐛 故障排查

### Python 后端无法启动
- 检查 `.env.tauri` 配置是否正确
- 确认 Python 依赖已安装：`uv sync --all-extras`
- 查看日志：`~/.myrmagent/logs/`

### Tauri 构建失败
- 确认 Rust 工具链已安装：`rustc --version`
- 更新 Tauri CLI：`cargo install tauri-cli --force`
- 清理缓存：`cargo clean`

### 前端静态导出问题
- 确认使用了 `BUILD_MODE=tauri` 环境变量
- 检查是否有不兼容的动态路由或 API routes
- 查看构建日志：`bun run build:tauri`

## 📊 性能优化

### 减小打包体积
1. **Python 后端**:
   - 使用 `--exclude-module` 排除不需要的库
   - 使用 UPX 压缩：`upx --best myrmagent-backend`

2. **Tauri 应用**:
   - 启用 LTO：在 `Cargo.toml` 中设置 `lto = true`
   - 使用 `strip` 移除调试符号

### 启动速度优化
- 延迟加载非关键模块
- 使用 Tauri 的 `async` 启动
- 预热数据库连接池

## 📝 开发注意事项

1. **静态导出限制**:
   - 不支持 Next.js API routes
   - 不支持服务端组件（RSC）
   - 图片需要 `unoptimized: true`

2. **跨平台兼容**:
   - 路径使用 `Path` 而不是字符串拼接
   - 文件权限在 Windows 上可能不同
   - 测试所有目标平台

3. **安全性**:
   - 所有数据存储在 `~/.myrmagent/`
   - 不要硬编码 API Key
   - 使用 Tauri 的安全 API

## 🔗 相关链接

- [Tauri 文档](https://tauri.app/)
- [PyInstaller 文档](https://pyinstaller.org/)
- [Next.js 静态导出](https://nextjs.org/docs/app/building-your-application/deploying/static-exports)
- [架构文档](../ARCHITECTURE.md)
