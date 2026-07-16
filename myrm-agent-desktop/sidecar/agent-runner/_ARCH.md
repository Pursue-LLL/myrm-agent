# agent-runner 模块架构

[INPUT]
- 外部 CLI（claude / codex / gemini 等）stdin/stdout

[OUTPUT]
- agent-runner-* 独立二进制（JSON-RPC stdio 服务）

[POS]
Agent Runner Sidecar **源码**。运行时 JSON-RPC 管理见 src-tauri/src/agent_runner_rpc/。

## 架构概述

CLI Agent Runner Sidecar 源码：stdin/stdout JSON-RPC，桥接外部 CLI（Claude Code 等）与 Tauri WebView。

构建：`sidecar/build.py`（`bun build --compile`）→ `src-tauri/binaries/agent-runner-*`  
本地开发：`bun run dev`（直接执行 `src/index.ts`，不经 `dist/`）  
运行时管理：[../../src-tauri/src/agent_runner_rpc/_ARCH.md](../../src-tauri/src/agent_runner_rpc/_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `src/` | 核心 | JSON-RPC 实现 → [src/_ARCH.md](src/_ARCH.md) | — |
| `package.json` | 配置 | Bun 依赖与 compile 脚本 | — |

## 依赖

- Bun >= 1.1
- 父构建入口：[../_ARCH.md](../_ARCH.md)
