# memory/ 模块架构

## 架构概述

`@/services/memory` 分片实现：记忆 CRUD 核心、归档、Personal Brain Command Center、偏好、Shared Context、健康探测、Integration Memory。`memory.ts`（根）为 facade re-export。

## 文件清单

| 文件                | 职责                                                                                                              |
| ------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `core.ts`           | Memory API DTO 与 CRUD/export/guardian health/policy/digest/rating/status/taste/trash/working-state helper        |
| `archive.ts`        | Typed Memory Archive export/restore 与 server-bound memory import 请求（dry-run/confirm + post-import readiness） |
| `commandCenter.ts`  | Personal Brain Command Center：GUI 治理动作、可执行诊断、迁移完整性状态、导入清理指标                             |
| `externalTranscripts.ts` | 外部 Agent 转录增量同步 API：状态查询与增量同步触发（本地/上传）                                      |
| `preferences.ts`    | Memory preference facet：生命周期 DTO 与列表 API                                                                  |
| `sharedContexts.ts` | Shared Context：状态/提案 DTO、目标绑定、CRUD                                                                     |
| `health.ts`         | Shared Context 记忆依赖健康探测                                                                                   |
| `integration.ts`    | Integration Memory：sync / browse / status                                                                        |

## 依赖

- `@/lib/api`
- `memory/core.ts`（commandCenter 复用 `MemoryType`；archive 复用 `MemoryImportSource`）
- 父模块 [services/_ARCH.md](../_ARCH.md)
