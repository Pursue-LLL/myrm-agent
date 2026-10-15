# memory/ 模块架构

## 架构概述

`@/services/memory` 分片实现：记忆 CRUD 核心、归档、Personal Brain Command Center、偏好、Shared Context、健康探测、Integration Memory。`memory.ts`（根）为 facade re-export。

## 文件清单

| 文件                     | 职责                                                                                                              |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `core.ts`                | Memory API DTO 与 CRUD/export/guardian health/policy/digest/rating/status/taste/trash/working-state helper        |
| `pendingTargetChanged.ts` | 判定批准失败是否因建议所针对的记忆在入队后已变化（HTTP 409），供 UI 展示本地化「已过期」提示 |
| `archive.ts`             | Typed Memory Archive export/restore 与 server-bound memory import 请求（dry-run/confirm + post-import readiness） |
| `commandCenter.ts`       | Personal Brain Command Center：GUI 治理动作、可执行诊断、迁移完整性状态、导入清理指标                             |
| `externalTranscripts.ts` | 外部 Agent 转录增量同步 API：状态查询与增量同步触发（本地/上传）                                                  |
| `preferences.ts`         | Memory preference facet：生命周期 DTO 与列表 API                                                                  |
| `sharedContexts.ts`      | Shared Context：状态/提案 DTO、目标绑定、CRUD                                                                     |
| `health.ts`              | Shared Context 记忆依赖健康探测                                                                                   |
| `integration.ts`         | Integration Memory：sync / browse / status                                                                        |
| `cognitiveClock.ts`      | 嵌套多频认知时钟客户端：时钟调度状态查询、用户活跃通知上报与 T1 会话防抖手动提炼触发                              |
| `quadrupleRetrieval.ts` | 目标驱动四路并行检索与推理重排客户端：四路并行召回、前置意图解构与 Reasoner 决策指标                               |
| `sqliteVec.ts`          | 基于SQLite与sqlite-vec的嵌入式轻量向量存储客户端：零守护进程、单文件自包含、双轨执行模式监控与时间衰减稠密检索 |
| `vectorSpaceGuard.ts`   | Embedding模型维度与向量空间完整性校验守卫客户端：预检兼容性、模型底模与维度对齐、指纹绑定与安全重建索引 |
| `markdownChunker.ts`    | 增量滑动窗口Markdown切片与重叠索引管道客户端：400-token滑动窗口切片、80-token重叠、行级回溯水合与增量Token节省率分析 |
| `hybridSearch.ts`       | 双引擎FTS与向量混合重排与平滑降级客户端：自适应多因子RRF重排、Ebbinghaus衰减、认知重要性加权与向量断路器遥测 |
| `memoryMigration.ts`    | 全平台多格式记忆无缝迁移与导入引擎客户端：OpenClaw/Hermes/ChatGPT/Claude/MemOS/Markdown资产探测、认知层级映射预览、400/80滑动窗口切片导入与幂等去重 |
| `experienceCompounding.ts` | 个人经验资产复利演进与自动凝练客户端：有界对数加固、高阶黄金准则语义凝练提炼、谱系回退与冷数据退火治理 |


## 依赖

- `@/lib/api`
- `memory/core.ts`（commandCenter 复用 `MemoryType`；archive 复用 `MemoryImportSource`）
- 父模块 [services/_ARCH.md](../_ARCH.md)
