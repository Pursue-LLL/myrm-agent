# lib/connection/

## 架构概述

2 个源文件（2 个辅助）。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `connection-controller.ts` | 辅助 | 导出 `ConnectionController`；类型 `ConnectionStatus`、`ConnectionStateListener`、`ConnectionControllerOptions` | — |
| `jitter-backoff.ts` | 辅助 | 导出 `JitteredBackoffScheduler`；类型 `BackoffOptions` | — |

## 依赖

- 无目录外依赖
