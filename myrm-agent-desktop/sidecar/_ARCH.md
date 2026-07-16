# sidecar 模块架构

[INPUT]
- myrm-agent-server/app/main.py（POS: Python 后端入口）
- sidecar/agent-runner/（POS: Agent Runner TS 源码）

[OUTPUT]
- src-tauri/binaries/myrmagent-backend-*
- src-tauri/binaries/agent-runner-*

[POS]
Sidecar **构建**入口（非运行时）。运行时进程管理在 src-tauri/src/runtime/ 与 agent_runner_rpc/。

## 架构概述

Tauri Desktop Sidecar 构建入口：PyInstaller 打包 Python 后端 + Bun compile Agent Runner 为独立二进制。

## 使用方法

```bash
python build.py
```

## 产出

平台二进制输出至 `../src-tauri/binaries/`：

| 组件 | macOS | Linux | Windows |
|------|-------|-------|---------|
| Python Backend | `myrmagent-backend-aarch64-apple-darwin` | `myrmagent-backend-x86_64-unknown-linux-gnu` | `myrmagent-backend-x86_64-pc-windows-msvc.exe` |
| Agent Runner | `agent-runner-aarch64-apple-darwin` | `agent-runner-x86_64-unknown-linux-gnu` | `agent-runner-x86_64-pc-windows-msvc.exe` |

## 技术细节

- **后端入口**: `myrm-agent-server/app/main.py`
- **打包**: PyInstaller `--onefile`，并 `--add-data` 打入 `shared/config/provider_legacy_remap.json`（供 server provider remap）
- **环境变量**: `WEBUI_MODE`、`WEBUI_REMOTE_MODE`、`PORT`（Desktop 8080 / WebUI 25808）

## 运行模式

| 模式 | 绑定 | 用途 |
|------|------|------|
| Desktop Sidecar | `127.0.0.1:8080` | Tauri 内嵌后端 |
| WebUI Local | `127.0.0.1:25808` | 本机浏览器 |
| WebUI Remote | `0.0.0.0:25808` | 局域网/外网（需密码） |

## 依赖

- Python 3.13+、PyInstaller、Bun >= 1.1
- Harness 经 `uv sync` 从 PyPI 安装
- 父模块 [myrm-agent-desktop/_ARCH.md](../_ARCH.md)
