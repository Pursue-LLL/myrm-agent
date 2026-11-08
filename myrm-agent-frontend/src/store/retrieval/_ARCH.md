# store/retrieval/ 模块架构

## 架构概述

`useRetrievalStore`（嵌入 / 重排序模型配置，及更换嵌入模型后旧记忆迁移的运行状态）的组成部分：类型、初始状态、与 `ConfigSyncManager` 的同步桥。Store 本体在上一级 `../useRetrievalStore.ts`，校验应用与迁移轮询这些带副作用的动作留在本体里。

## 文件清单

| 文件             | 职责                                                                                                                                                  |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`       | `ApplyStatus`、`ProviderModelConfig`、`RetrievalConfig`、`ReindexRunStatus`，以及 store 整体类型 `RetrievalStore`（配置状态 + 动作）                  |
| `defaults.ts`    | `DEFAULT_CONFIG`：全部配置字段的初始值（默认服务商及其预设模型）；`reset` 与加载缺省值共用                                                            |
| `persistence.ts` | `syncToManager`：把已生效的检索配置交给 `ConfigSyncManager`（防抖同步）；`estimateOrphansOnceSaved`：强制同步，保存成功后才估算旧记忆，保存失败则跳过 |

## 依赖

- `@/services/config` — `ConfigSyncManager`、`RetrievalConfigValue`
- `@/services/memory/reindex` — `MemoryReindexResult` 类型
- `@/lib/search/retrievalProviders` — 默认服务商与预设模型

## 约束

- 类型一律从 `@/store/retrieval/types` 引用，`useRetrievalStore.ts` 不转出类型
- 本目录只放类型、常量与无 store 引用的辅助函数；读写 store 状态的动作留在 `useRetrievalStore.ts`
