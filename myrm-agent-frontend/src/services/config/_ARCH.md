# services/config（前端）

## 架构概述

统一用户配置同步层：`ConfigSyncManager` 为唯一写入网关，Store 为 reactive view。
支持 Tauri（SQLite）与 Sandbox（PostgreSQL + 服务端加密）两种部署模式。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                               | I/O/P |
| ------------------------------ | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `ConfigSyncManager.ts`         | 核心 | 乐观锁同步、离线队列、分级冲突消解、`commitIfDirty`、`runStartupNormalization`、`ensureKeyLoaded`（渐进加载下读取前确保目标 key 已同步）、后台预加载完成通知订阅者 | ✅    |
| `configNormalizer.ts`          | 核心 | 启动归一化管道（providers / personalSettings）                                                                                                                     | ✅    |
| `configFingerprint.ts`         | 辅助 | 稳定 fingerprint / deep equal，跳过 no-op 写入                                                                                                                     | ✅    |
| `themePersonalSettingsSync.ts` | 辅助 | 检测 personalSettings 主题字段变更，触发 ConfigSync fast-path                                                                                                      | ✅    |
| `configInitLock.ts`            | 辅助 | Web Locks API，单 tab 执行启动迁移写                                                                                                                               | ✅    |
| `mergeUtils.ts`                | 辅助 | 三向深度合并                                                                                                                                                       | ✅    |
| `types.ts`                     | 核心 | ConfigKey 枚举、默认值、版本号工具                                                                                                                                 | ✅    |
| `adapters/TauriAdapter.ts`     | 适配 | 本地 HTTP → SQLite                                                                                                                                                 | ✅    |
| `adapters/SandboxAdapter.ts`   | 适配 | 云端 API → PostgreSQL                                                                                                                                              | ✅    |
| `adapters/BaseAdapter.ts`      | 适配 | deviceId、版本号基类                                                                                                                                               | ✅    |
| `index.ts`                     | 核心 | ConfigSync 公共 API barrel（`@/services/config`）                                                                                                                  | ✅    |

## 主题持久化 fast-path

`personalSettings` 内 `activeThemeProfileId` / `themeProfiles` / `themeFontOverride` 变更时：

1. `saveOfflineQueue(changeQueue)` — 关 tab 前落盘待同步队列
2. 跳过 1s debounce，立即 `flushSync()`

`securityConfig` 同样走 fast-path：安全关键变更（如 YOLO 关闭）立即持久化，避免
1s debounce 内关 tab/刷新丢失，造成「UI 显示已关闭但后端仍开启」的安全假象。

非主题字段仍走常规 debounce。见 `themePersonalSettingsSync.ts` + `ConfigSyncManager.set()`.

## 渐进加载与订阅通知

Sandbox 模式下 `initialize()` 只 await 核心 key（providers/chatSettings/personalSettings），
其余 key（含 `securityConfig`）后台异步预加载。预加载写入缓存时**同步通知订阅者**——
否则「配置就绪后兜底」类逻辑（如 securityConfig ⇄ YOLO 互斥重放）永远收不到触发。
读取即决策的安全敏感路径应使用 `ensureKeyLoaded(key)` 显式等待目标 key 同步。

## 写入一致性（offline replay）

- `initialize()` 重放 offline queue **前**：`applyPendingChangesToCache` 乐观写入 cache（与 `set()` 同语义）
- `flushSync()` 成功 **后**：`mergedChanges[].value` 同步到 `cache` + `baseCache`

保证 `initConfig` 读到的 `personalSettings` 与最后一次本地写入一致，reload 不闪回旧肤。

## 冲突消解分级

| Tier | 条件                   | 行为                   |
| ---- | ---------------------- | ---------------------- |
| T0   | fingerprint 相同       | 不写入                 |
| T1   | 三向合并成功           | 静默合并               |
| T2   | 同 `deviceId` 版本冲突 | 静默保留本地           |
| T3   | 跨设备同字段冲突       | `ConfigConflictDialog` |

## 依赖

- `@/store/config/*` — 类型与迁移函数（providerIdentityMigration）
- `@/components/features/app-shell/settings-sync-initializer.tsx` — 应用顶层初始化
- `@/components/features/app-shell/ConfigConflictDialog.tsx` — T3 冲突 UI
