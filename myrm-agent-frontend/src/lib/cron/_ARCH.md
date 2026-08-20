# lib/cron/

## 架构概述

Cron 相关纯函数：Hermes 六字段审计快照、Settings 创建 pause/confirm/resume 门禁策略。

## 文件清单

| 文件                      | 地位 | 职责                                                                                                                     | I/O/P |
| ------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------ | ----- |
| `buildCronAuditFields.ts` | 核心 | 六字段 audit 快照 + localStorage confirm                                                                                 | ✅    |
| `cronCreateAuditGate.ts`  | 核心 | Settings audit policy + pause/resume gate                                                                                | ✅    |
| `schedulerHealth.ts`      | 核心 | `GET /cron/scheduler/health` single-flight fetch + subscribe；backend 未就绪时 skip poll；Badge 与 AppLayout banner 共用 | ✅    |
| `__tests__/`              | 测试 | vitest 单元测试                                                                                                          | 内联  |

## 依赖

- `@/services/cron` — pause/resume/get
- `@/services/cron.types` — CronJob
- 消费方：[`components/features/cron/`](../components/features/cron/_ARCH.md)

## 约束

- 无 React；可单元测试
- 禁止桶导出
