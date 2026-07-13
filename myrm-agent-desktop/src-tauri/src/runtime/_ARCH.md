# runtime 模块架构

## 架构概述

Tauri 主进程内的 Sidecar 与系统运行时层：Python/Next.js/Agent Runner 进程生命周期、全局快捷键、Setup Token、端口检测。

父模块：[../../_ARCH.md](../../_ARCH.md) · [../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 模块聚合、`suppress_console_window` | ✅ |
| `python_backend.rs` | 核心 | Python Sidecar 启停与健康检查 | ✅ |
| `nextjs_frontend.rs` | 核心 | Next.js Standalone 进程（Tauri 启动时始终自启） | — |
| `watchdog.rs` | 核心 | 后端崩溃监控与指数退避重启 | ✅ |
| `agent_runner.rs` | 核心 | Agent Runner 路径解析与事件桥接 | ✅ |
| `setup_token.rs` | 核心 | WebUI Remote Setup Token IPC | — |
| `port.rs` | 工具 | 端口占用检测 | — |
| `inline_input.rs` | 核心 | Inline Input 全局快捷键与 paste_back | ✅ |
| `appshot/` | 核心 | Appshot 截屏、Voice PTT、窗口 toggle | ✅ |

## 依赖

- `config` — BackendConfig / FrontendConfig / SystemConfig
- `sidecar` — Agent Runner JSON-RPC
- `commands::agent` — AgentSystemState
