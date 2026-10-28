# services/config（前端）

## 架构概述

统一用户配置同步层：`ConfigSyncManager` 为唯一写入网关，Store 为 reactive view。
支持 Tauri（SQLite）与 Sandbox（PostgreSQL + 服务端加密）两种部署模式。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | I/O/P |
| ------------------------------ | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ConfigSyncManager.ts`         | 核心 | 配置的唯一写入网关：乐观更新缓存、防抖 / fast-path 同步、`commitIfDirty`、`ensureKeyLoaded`（渐进加载下读取前确保目标 key 已同步）、后台预加载完成通知订阅者；离线队列、冲突消解、首屏加载、订阅分发、启动归一化各自落在下面的独立模块里，管理器只持有缓存与队列状态并调度它们。**密钥丢失的行不回写**：服务端把「已加密存储但封存它的密钥已丢失」的行标成 `unreadable`（值为空），`commitIfDirty` / 启动归一化对这样的键不回写默认值，只有用户显式保存才覆盖；`getUnreadableKeys()` 列出这些键供横幅提示 | ✅    |
| `offlineQueue.ts`              | 核心 | 离线队列的浏览器存储：**落盘只收白名单键**，含密钥的键只在内存队列里重试，不写 `localStorage`；队列合并保留最早的基准版本；`takeUnpersistableOfflineEntries()` 在管理器启动时（先于后端可达性检查）把存储里已有的非白名单条目移出存储、交给内存等待重放；`isNetworkError` / `isRecoverableSyncError` 区分可稍后重试的失败                                                                                                                                                                                 | ✅    |
| `offlineReplay.ts`             | 核心 | 离线重放决策（纯函数）：**过期闸门**——队列里的变更记录了它当初与服务端分叉的基准版本，重放前与服务端当前版本比对，服务端已前进则判为过期（默认保留服务端值，注册了冲突解决器时交由用户决定），避免陈旧快照覆盖服务端新配置；`mergeLatestChanges` 每个 key 取最新值                                                                                                                                                                                                                                        | ✅    |
| `conflictResolution.ts`        | 核心 | 版本冲突分级消解（见下表）与冲突解决器类型；通过 `ConflictContext` 接收管理器的缓存与回调，自身无状态；重试仍失败时变更放回队列，本地值不丢                                                                                                                                                                                                                                                                                                                                                               | ✅    |
| `initialLoad.ts`               | 核心 | 首屏加载：失败重试 3 次；Sandbox 模式先取核心 key、其余以延迟启动的 thunk 交还管理器后台预加载，本地模式一次取全                                                                                                                                                                                                                                                                                                                                                                                          | ✅    |
| `configListeners.ts`           | 辅助 | 按 key 的订阅者注册表，单个订阅者抛错不影响其余订阅者                                                                                                                                                                                                                                                                                                                                                                                                                                                     | ✅    |
| `startupNormalization.ts`      | 辅助 | 启动归一化遍历（Web Lock 内），写入走管理器的 `commitIfDirty`，因此不会覆盖读不出的密文行                                                                                                                                                                                                                                                                                                                                                                                                                 | ✅    |
| `e2eSearchSyncGate.ts`         | 辅助 | E2E 测试开关：E2E 运行里搜索配置只留在本地，不进同步队列也不通知订阅者；未设置标志时为空操作                                                                                                                                                                                                                                                                                                                                                                                                              | ✅    |
| `offlinePersistableKeys.ts`    | 核心 | 离线队列允许明文落盘的配置键白名单（仅服务端也不加密存储的键）。白名单而非黑名单：新增键默认不落盘；服务端 `tests/architecture/test_offline_persistable_keys_parity.py` 保证它恰好等于前端全部配置键减去 `SENSITIVE_CONFIG_KEYS`                                                                                                                                                                                                                                                                          | ✅    |
| `configNormalizer.ts`          | 核心 | 启动归一化管道（providers / personalSettings）；`dropNullFields`：服务端会把未设置的字段存成 null，归一化与 `useConfigStore` 订阅都把 null 当作未设置而保留默认值（否则列表型默认字段变 null，设置页读 `.length` 崩溃）                                                                                                                                                                                                                                                                                   | ✅    |
| `configFingerprint.ts`         | 辅助 | 稳定 fingerprint / deep equal，跳过 no-op 写入                                                                                                                                                                                                                                                                                                                                                                                                                                                            | ✅    |
| `themePersonalSettingsSync.ts` | 辅助 | 检测 personalSettings 主题字段变更，触发 ConfigSync fast-path                                                                                                                                                                                                                                                                                                                                                                                                                                             | ✅    |
| `configInitLock.ts`            | 辅助 | Web Locks API，单 tab 执行启动迁移写                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | ✅    |
| `mergeUtils.ts`                | 辅助 | 三向深度合并                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | ✅    |
| `types.ts`                     | 核心 | ConfigKey 枚举、默认值、版本号工具                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | ✅    |
| `adapters/TauriAdapter.ts`     | 适配 | 本地 HTTP → SQLite                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | ✅    |
| `adapters/SandboxAdapter.ts`   | 适配 | 云端 API → PostgreSQL                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | ✅    |
| `adapters/BaseAdapter.ts`      | 适配 | deviceId、版本号基类                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | ✅    |
| `index.ts`                     | 核心 | ConfigSync 公共 API barrel（`@/services/config`）                                                                                                                                                                                                                                                                                                                                                                                                                                                         | ✅    |

## 内置 provider 合并

`configNormalizer.ts` 的 `BUILT_IN_FIELD_OWNER` 为 `ProviderConfig` 的每个字段声明归属（出厂定义 / 用户保存值），类型上对全部字段穷举，新增字段时编译期强制作出决定；`mergeBuiltInProvider` 据此保留用户字段（启用状态、密钥、基址、模型选择、密钥池策略、订阅登录标志 `oauthConnected`、出口代理），其余取出厂定义。漏掉的字段会在每次启动被重置为出厂值。

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
