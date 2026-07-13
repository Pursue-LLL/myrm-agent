# agent-runner 模块架构

## 架构概述

CLI Agent Runner Sidecar 源码：stdin/stdout JSON-RPC，桥接外部 CLI（Claude Code 等）与 Tauri WebView。

构建：`sidecar/build.py` → `bun build --compile` → `src-tauri/binaries/agent-runner-*`  
运行时管理：[../../src-tauri/src/sidecar/_ARCH.md](../../src-tauri/src/sidecar/_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `src/index.ts` | 核心 | JSON-RPC 服务入口、readline 循环 | — |
| `src/runner.ts` | 核心 | Agent 检测、会话、消息、权限 | — |
| `src/types.ts` | 核心 | RPC 与 Session 类型定义 | — |
| `package.json` | 配置 | Bun 依赖与 compile 脚本 | — |

## 依赖

- Bun >= 1.1
- 父构建入口：[../_ARCH.md](../_ARCH.md)
