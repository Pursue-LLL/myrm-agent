# commands/agent 模块架构

[INPUT]
- agent_runner_rpc::SidecarManager（POS: Agent Runner JSON-RPC 进程）
- sessions::SessionManager / permissions::PermissionManager
- cli_agent_types（POS: AdapterInfo / PermissionMode）

[OUTPUT]
- CLI Agent Tauri IPC：会话 CRUD、消息发送/停止、权限模式、Sidecar 状态

[POS]
CLI 可视化 IPC 子模块；唯一执行路径经 Agent Runner JSON-RPC，不经 Python 后端。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | AgentSystemState、SidecarStatus、IPC 聚合 | — |
| `session.rs` | 核心 | 会话 CRUD IPC | — |
| `message.rs` | 核心 | 消息发送/停止 IPC | — |
| `permission.rs` | 核心 | 权限模式 IPC | — |

## 依赖

- [../_ARCH.md](../_ARCH.md) — commands 父模块
- [../../agent_runner_rpc/_ARCH.md](../../agent_runner_rpc/_ARCH.md) — JSON-RPC 运行时
- [../../sessions/_ARCH.md](../../sessions/_ARCH.md) · [../../permissions/_ARCH.md](../../permissions/_ARCH.md)
