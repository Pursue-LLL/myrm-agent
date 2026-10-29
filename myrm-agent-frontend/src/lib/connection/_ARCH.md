# lib/connection/

## 架构概述

2 个源文件（2 个辅助）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `connection-controller.ts` | 辅助 | 导出 `ConnectionController`；类型 `ConnectionStatus`、`ConnectionStateListener`、`ConnectionControllerOptions` | — |
| `jitter-backoff.ts` | 辅助 | 导出 `JitteredBackoffScheduler`；类型 `BackoffOptions` | — |

## 依赖

- 无目录外依赖
