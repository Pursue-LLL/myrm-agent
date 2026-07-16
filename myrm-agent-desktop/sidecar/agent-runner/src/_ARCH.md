# agent-runner/src 模块架构

[INPUT]
- 外部 CLI 进程 stdin/stdout（claude / codex / gemini 等）
- JSON-RPC 请求（method / params）经 readline stdio

[OUTPUT]
- JSON-RPC 响应与 Agent 事件通知（text / tool_call / permission_request 等）

[POS]
Agent Runner Sidecar **实现**叶子目录；包级说明见 [../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 核心 | JSON-RPC 服务入口、readline 循环 | — |
| `runner.ts` | 核心 | Agent 检测、会话、消息、权限桥接 | — |
| `types.ts` | 核心 | RPC 与 Session 类型定义 | — |

## 依赖

- Bun >= 1.1
- 运行时管理：[../../../src-tauri/src/agent_runner_rpc/_ARCH.md](../../../src-tauri/src/agent_runner_rpc/_ARCH.md)
