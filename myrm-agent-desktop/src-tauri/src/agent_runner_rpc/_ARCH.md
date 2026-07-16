# agent_runner_rpc 模块架构

[INPUT]
- sidecar/agent-runner 编译产物或 dev 下 bun/ts 入口
- runtime::TOXIC_ENV_VARS（POS: 子进程环境清洗）

[OUTPUT]
- SidecarManager: JSON-RPC stdio 请求/通知、事件 broadcast

[POS]
Agent Runner **运行时** JSON-RPC 进程管理。勿与 sidecar/（构建脚本）混淆。

## 架构概述

Agent Runner **运行时** JSON-RPC 进程管理：启动 Bun compile 二进制，stdio 通信，事件 broadcast。

> 勿与仓库根 `sidecar/`（**构建**脚本）混淆。对照表见 [../../../_ARCH.md](../../../_ARCH.md)。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | SidecarManager 生命周期、JSON-RPC call | ✅ |
| `types.rs` | 核心 | SidecarEvent、RPC 协议帧类型 | ✅ |
| `transport.rs` | 核心 | stdout 读取、agent.event 转发 | ✅ |

## 依赖

- `cli_agent_types` — 共享序列化类型
- 源码构建产物：`sidecar/agent-runner/` → `src-tauri/binaries/agent-runner-*`
