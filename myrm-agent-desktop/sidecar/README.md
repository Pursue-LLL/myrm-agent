# Sidecar Builder

## 功能

将所有 Sidecar 打包为独立可执行文件，作为 Tauri Desktop 的 Sidecar 进程运行：

1. **Python Backend** — PyInstaller 打包 FastAPI 后端
2. **Agent Runner** — `bun build --compile` 编译 TypeScript CLI 工具为独立二进制（无需系统 Node.js）

## 使用方法

```bash
python build.py
```

## 输出

生成平台特定的二进制文件，位于 `../src-tauri/binaries/`：

### Python Backend
- **macOS**: `myrmagent-backend-aarch64-apple-darwin`
- **Linux**: `myrmagent-backend-x86_64-unknown-linux-gnu`
- **Windows**: `myrmagent-backend-x86_64-pc-windows-msvc.exe`

### Agent Runner
- **macOS**: `agent-runner-aarch64-apple-darwin`
- **Linux**: `agent-runner-x86_64-unknown-linux-gnu`
- **Windows**: `agent-runner-x86_64-pc-windows-msvc.exe`

## 工作原理

1. **入口文件**: `myrm-agent-server/app/main.py`
2. **打包工具**: PyInstaller (`--onefile` 模式)
3. **环境变量支持**:
   - `WEBUI_MODE`: 启用 WebUI 模式
   - `WEBUI_REMOTE_MODE`: 启用远程访问
   - `PORT`: 服务端口（Desktop: 8080, WebUI: 25808）

## 运行模式

### Desktop Sidecar 模式
- 绑定: `127.0.0.1:8080`
- 用途: Tauri 桌面应用后端

### WebUI Local 模式
- 绑定: `127.0.0.1:25808`
- 用途: 本机浏览器访问

### WebUI Remote 模式
- 绑定: `0.0.0.0:25808`
- 用途: 局域网/外网访问
- 安全: 需要密码认证

## 依赖

- Python 3.13+ + PyInstaller（Backend Sidecar）
- Bun >= 1.1（Agent Runner 编译）
- Harness：默认经 `scripts/dev/install_harness_dev.sh` 从 [PyPI](https://pypi.org/project/myrm-agent-harness/) 安装；本地 harness 开发可设 `MYRM_HARNESS_INSTALL_MODE=source` 或 `MYRM_HARNESS_EDITABLE=1`
- 所有 FastAPI 后端依赖（自动打包）
- Agent Runner 依赖由 `bun install` 自动安装
