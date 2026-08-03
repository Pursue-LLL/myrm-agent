# services/config（前端）

## 架构概述

统一用户配置同步层：`ConfigSyncManager` 为唯一写入网关，Store 为 reactive view。
支持 Tauri（SQLite）与 Sandbox（PostgreSQL + 服务端加密）两种部署模式。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ConfigSyncManager.ts` | 核心 | 乐观锁同步、离线队列、分级冲突消解、`commitIfDirty`、`runStartupNormalization` | ✅ |
| `configNormalizer.ts` | 核心 | 启动归一化管道（providers / personalSettings） | ✅ |
| `configFingerprint.ts` | 辅助 | 稳定 fingerprint / deep equal，跳过 no-op 写入 | ✅ |
| `themePersonalSettingsSync.ts` | 辅助 | 检测 personalSettings 主题字段变更，触发 ConfigSync fast-path | ✅ |
| `configInitLock.ts` | 辅助 | Web Locks API，单 tab 执行启动迁移写 | ✅ |
| `mergeUtils.ts` | 辅助 | 三向深度合并 | ✅ |
| `types.ts` | 核心 | ConfigKey 枚举、默认值、版本号工具 | ✅ |
| `adapters/TauriAdapter.ts` | 适配 | 本地 HTTP → SQLite | ✅ |
| `adapters/SandboxAdapter.ts` | 适配 | 云端 API → PostgreSQL | ✅ |
| `adapters/BaseAdapter.ts` | 适配 | deviceId、版本号基类 | ✅ |
| `index.ts` | 核心 | ConfigSync 公共 API barrel（`@/services/config`） | ✅ |

## 主题持久化 fast-path

`personalSettings` 内 `activeThemeProfileId` / `themeProfiles` / `themeFontOverride` 变更时：

1. `saveOfflineQueue(changeQueue)` — 关 tab 前落盘待同步队列
2. 跳过 1s debounce，立即 `flushSync()`

非主题字段仍走常规 debounce。见 `themePersonalSettingsSync.ts` + `ConfigSyncManager.set()`.

## 写入一致性（offline replay）

- `initialize()` 重放 offline queue **前**：`applyPendingChangesToCache` 乐观写入 cache（与 `set()` 同语义）
- `flushSync()` 成功 **后**：`mergedChanges[].value` 同步到 `cache` + `baseCache`

保证 `initConfig` 读到的 `personalSettings` 与最后一次本地写入一致，reload 不闪回旧肤。

## 冲突消解分级

| Tier | 条件 | 行为 |
|------|------|------|
| T0 | fingerprint 相同 | 不写入 |
| T1 | 三向合并成功 | 静默合并 |
| T2 | 同 `deviceId` 版本冲突 | 静默保留本地 |
| T3 | 跨设备同字段冲突 | `ConfigConflictDialog` |

## 依赖

- `@/store/config/*` — 类型与迁移函数（providerIdentityMigration）
- `@/components/features/app-shell/settings-sync-initializer.tsx` — 应用顶层初始化
- `@/components/features/app-shell/ConfigConflictDialog.tsx` — T3 冲突 UI
