# runtime 模块架构

[INPUT]
- config（POS: BackendConfig / FrontendConfig / SystemConfig）
- agent_runner_rpc（POS: Agent Runner JSON-RPC 进程）

[OUTPUT]
- Python / Next.js / Agent Runner Sidecar 启停与健康检查
- Appshot / Voice PTT / Inline Input 全局快捷键

[POS]
Tauri 主进程 Sidecar 与系统运行时层。

## 架构概述

Tauri 主进程内的 Sidecar 与系统运行时层：Python/Next.js/Agent Runner 进程生命周期、全局快捷键、Setup Token、端口检测。

父模块：[../../_ARCH.md](../../_ARCH.md) · [../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 模块聚合、`TOXIC_ENV_VARS` 毒性环境变量黑名单、`suppress_console_window` | ✅ |
| `sidecar_version_manager.rs` | 核心 | Sidecar 独立引擎版本状态机（versions.json、原子写入、三级降级链路与坏版本拉黑） | ✅ |
| `python_backend.rs` | 核心 | Python Sidecar 启停、版本自适应解析、就绪探测与启动超时自动回滚自愈 | ✅ |
| `nextjs_frontend.rs` | 核心 | Next.js Standalone 进程（Tauri 启动时始终自启） | — |
| `watchdog.rs` | 核心 | 后端崩溃监控与指数退避重启 | ✅ |
| `agent_runner.rs` | 核心 | Agent Runner 路径解析与事件桥接 | ✅ |
| `setup_token.rs` | 核心 | WebUI Remote Setup Token IPC | — |
| `port.rs` | 工具 | 端口占用检测 | — |
| `survivor_diag.rs` | 核心 | 端口幸存者诊断与安全 Re-kill 自愈回收 | ✅ |
| `process_registry/` | 核心 | 桌面受管进程注册中心（多 Sidecar 全生命周期追踪与定向销毁） | ✅ |
| `inline_input.rs` | 核心 | Inline Input 全局快捷键与 paste_back | ✅ |
| `appshot/` | 核心 | Appshot 截屏、Voice PTT、窗口 toggle | ✅ |

## 依赖

- `config` — BackendConfig / FrontendConfig / SystemConfig
- `agent_runner_rpc` — Agent Runner JSON-RPC
- `commands::agent` — AgentSystemState
