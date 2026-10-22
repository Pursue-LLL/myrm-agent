# memory/ 模块架构

## 架构概述

`@/services/memory` 分片实现：记忆 CRUD 核心、归档、Personal Brain Command Center、偏好、Shared Context、健康探测、Integration Memory。`memory.ts`（根）为 facade re-export。

## 文件清单

| 文件                      | 职责                                                                                                                                                                                                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `core.ts`                 | Memory API DTO 与 CRUD/export/guardian health/policy/digest/rating/status/taste/trash/working-state helper                                                                                                                                                                                       |
| `pendingTargetChanged.ts` | 判定批准失败是否因建议所针对的记忆在入队后已变化（HTTP 409），供 UI 展示本地化「已过期」提示                                                                                                                                                                                                     |
| `archive.ts`              | Typed Memory Archive export/restore 与 server-bound memory import 请求（dry-run/confirm + post-import readiness）；`MEMORY_IMPORT_SOURCE_IDS` 为导入源词汇表（对齐服务端 `app/schemas/memory/import_sources.py`）；`dryRunImportMemories` 支持 `useModelExtraction` 让粘贴通道用模型整理自由文本 |
| `commandCenter.ts`        | Personal Brain Command Center：GUI 治理动作、可执行诊断、迁移完整性状态、导入清理指标                                                                                                                                                                                                            |
| `externalTranscripts.ts`  | 外部 Agent 转录增量同步 API：状态查询与增量同步触发（本地/上传）                                                                                                                                                                                                                                 |
| `preferences.ts`          | Memory preference facet：生命周期 DTO 与列表 API                                                                                                                                                                                                                                                 |
| `sharedContexts.ts`       | Shared Context：状态/提案 DTO、目标绑定、CRUD                                                                                                                                                                                                                                                    |
| `health.ts`               | Shared Context 记忆依赖健康探测                                                                                                                                                                                                                                                                  |
| `integration.ts`          | Integration Memory：sync / browse / status                                                                                                                                                                                                                                                       |
| `cognitiveClock.ts`       | 嵌套多频认知时钟客户端：时钟调度状态查询、用户活跃通知上报与 T1 会话防抖手动提炼触发                                                                                                                                                                                                             |
| `markdownChunker.ts`      | 增量滑动窗口Markdown切片与重叠索引管道客户端：400-token滑动窗口切片、80-token重叠、行级回溯水合与增量Token节省率分析                                                                                                                                                                             |
| `reindex.ts`              | 更换嵌入模型后的孤儿记忆迁移客户端：估算（`GET /memory/reindex/estimate`）、202 启动（`POST /memory/reindex`，同一嵌入模型已有进行中则加入同一轮，另一模型的进行中为 409）与进度/结果轮询（`GET /memory/reindex/status`）；全部 `silent`，错误由 `useRetrievalStore` 归一成界面状态              |
| `competitorMigration.ts`  | 竞品智能体迁入客户端：嗅探本机 Hermes/Claude Code/Codex 资产（`detect-competitors`）并一键迁入记忆、技能与规则（`ingest-competitors`）                                                                                                                                                           |

## 依赖

- `@/lib/api`
- `memory/core.ts`（commandCenter 复用 `MemoryType`；archive 复用 `MemoryImportSource`）
- 父模块 [services/_ARCH.md](../_ARCH.md)
