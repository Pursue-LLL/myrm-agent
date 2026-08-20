# wiki/ 模块架构

## 架构概述

`@/services/wikiService` 分片实现：`/wiki/*` 客户端、源同步、区块标题、证据上下文解析、证据指标、query success 延迟确认。`wikiService.ts`（根）为 facade re-export。

## 文件清单

| 文件                                 | 职责                                                                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `service.ts`                         | `/wiki/*` 客户端：概念树/队列/导入/审批与 query；`buildWikiApiPath`/`buildWikiAssetUrl`；`queryWiki` 返回结构化 `source_snippets(level/path/section/snippet)` |
| `sourceSync.ts`                      | Wiki 源同步：配置 / 状态 / 结果                                                                                                                               |
| `sectionLabels.ts`                   | Wiki 区块标题 i18n key 解析（Chat/设置共享）                                                                                                                  |
| `evidenceContextCore.ts`             | Wiki 证据 query 上下文解析核心（chat `context_key` 回溯边界 + `turn_distance`），供输入 Hook 与流式发送链路复用统一口径                                       |
| `evidenceMetrics.ts`                 | `/statistics/wiki-evidence/*` 客户端：证据曝光/展开/核验停留/query attempt+success/负向结果事件上报与聚合摘要查询                                             |
| `evidenceQuerySuccessPendingCore.ts` | Chat steer query success 延迟确认核心：按 `chatId + expectedMessageId` 注册待确认 success，首个匹配业务 SSE 帧到达时消费                                      |

## 依赖

- `@/lib/api`（service/evidenceMetrics/sourceSync）
- `@/lib/wiki/claimStatusDisplay`（service 复用 `WikiClaimStatus`）
- `@/store/chat/types`（evidenceMetrics 复用 `WikiSourceLevel`）
- 父模块 [services/_ARCH.md](../_ARCH.md)
