# agent_runner_rpc 模块架构

## 架构概述

Agent Runner **运行时** JSON-RPC 进程管理：启动 Bun compile 二进制，stdio 通信，事件 broadcast。

> 勿与仓库根 `sidecar/`（**构建**脚本）混淆。对照表见 [../../../_ARCH.md](../../../_ARCH.md)。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | SidecarManager、JSON-RPC 请求/通知、进程生命周期、spawn 前毒性环境变量清洗 | ✅ |

## 依赖

- `cli_agent_types` — 共享序列化类型
- 源码构建产物：`sidecar/agent-runner/` → `src-tauri/binaries/agent-runner-*`
