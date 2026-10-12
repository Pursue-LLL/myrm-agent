# store/offline/

## 架构概述

离线优先数据暂存中心。基于浏览器原生 IndexedDB（带安全内存 Fallback），提供端到端加密随手记笔记、离线任务等草稿数据的可靠持久化入队、状态机流转（staged -> syncing -> synced / failed）、网络重试与订阅通知能力。

## 文件清单

| 文件                              | 职责                                                                                                                              |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `offlineStagingStore.ts`          | 核心存储实例：管理 IndexedDB 数据库 `myrm_offline_staging_db`、入队自动加密、订阅广播、增删查改、在线自动同步及失败指数重试机制 |
| `__tests__/offlineStagingStore.test.ts` | 单元测试：覆盖内存 Fallback 下数据添加、加密信封生成、状态推进、队列同步重试与订阅广播行为                                        |

## 依赖

- `@/lib/e2ee/offlineE2EECryptoBridge` — AES-GCM-256 + PBKDF2 本地信封加密桥
- 原生 IndexedDB API / Web Crypto API
